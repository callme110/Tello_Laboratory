"""
ring_task.py
────────────────────────────────────────────────────────────
将 detect_circle.py 中的状态机封装为可复用的 RingTask 类。

主要改动（相对于原 detect_circle.py）：
  1. 去除模块级 Tello 初始化和主循环，改为通过构造函数注入已连接的 Tello 对象
  2. 去除 cv2.imshow 调用（后台线程无 GUI 窗口）
  3. 通过 status_callback 向外（Flask/SocketIO）实时推送状态
  4. 提供 start() / stop() 接口，支持多次启停
  5. 状态机逻辑与 detect_circle.py 完全一致，参数保持同步

使用示例（在 Flask 中）：
    def on_status(data):
        socketio.emit('ring_status', data)

    task = RingTask(tello_instance, status_callback=on_status)
    task.start()   # 非阻塞，后台线程运行
    task.stop()    # 安全停止
"""

import cv2
import numpy as np
import threading
import time


class RingTask:
    """
    圆环穿越任务（状态机）。

    状态流转：
        IDLE ──start()──► SEARCHING
                            │ 发现圆环
                          CENTERING ── 连续 CONFIRM_FRAMES 帧对准
                            │
                          PASSING ── 前进 PASS_TIME 秒
                            │
                    ┌── SEARCHING（下一个圆环）
                    └── DONE（全部穿越）──► 自动降落 ──► IDLE
    """

    # ─── 颜色参数（用 ColorPicker.py 对实际圆环标定后修改）───────────────────
    HSV_LOWER = np.array([5,  120, 120])   # 橙色圆环参考值（H/S/V 下限）
    HSV_UPPER = np.array([25, 255, 255])   # 橙色圆环参考值（H/S/V 上限）

    # ─── 控制参数 ─────────────────────────────────────────────────────────────
    IMG_W          = 480    # 处理分辨率：宽（像素）
    IMG_H          = 360    # 处理分辨率：高（像素）
    MIN_AREA       = 800    # 有效轮廓最小面积（像素²），低于此视为噪声
    CENTER_TOL     = 35     # 对准容差（像素），x/y 偏差均 < 此值视为对准
    CONFIRM_FRAMES = 20     # 连续对准帧数阈值，达到后触发穿越（约 0.6 s）
    LOST_LIMIT     = 25     # CENTERING 中连续丢失帧数上限，超过后回到 SEARCHING
    KP             = 0.15   # 比例控制系数（P gain）
    MAX_CTRL       = 30     # 对准控制量上限（lr/ud，单位：cm/s，范围 0~100）
    PASS_SPEED     = 35     # 穿越前进速度（fb 轴，单位：cm/s）
    PASS_TIME      = 2.0    # 穿越持续时间（秒），按圆环间距调整
    SEARCH_YAW     = 20     # 搜索时偏航速度（yv 轴，单位：cm/s）
    TOTAL_RINGS    = 3      # 需穿越的圆环总数
    LOOP_DELAY     = 0.03   # 主循环延时（秒），约 33 fps

    # ─── 状态常量 ─────────────────────────────────────────────────────────────
    IDLE      = 'IDLE'
    SEARCHING = 'SEARCHING'
    CENTERING = 'CENTERING'
    PASSING   = 'PASSING'
    DONE      = 'DONE'

    def __init__(self, tello_obj, status_callback=None):
        """
        参数：
            tello_obj       : 已连接（且已 streamon）的 djitellopy.Tello 实例
            status_callback : func(dict) → 每次状态更新时调用，用于 WebSocket 推送
                              dict 字段见 _emit() 方法注释
        """
        self.me              = tello_obj
        self.status_callback = status_callback
        self._running        = False
        self._thread: threading.Thread | None = None

        # ─── 对外只读的实时状态 ───
        self.state         = self.IDLE
        self.rings_passed  = 0
        self.confirm_count = 0
        self.err_x         = 0
        self.err_y         = 0

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """
        启动穿环任务（非阻塞，后台线程运行）。
        返回 False 表示任务已在运行，无需重复启动。
        注意：调用前请确保 Tello 已 takeoff 并 streamon。
        """
        if self._running:
            return False
        self._running      = True
        self.state         = self.SEARCHING
        self.rings_passed  = 0
        self.confirm_count = 0
        self.err_x         = 0
        self.err_y         = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """外部请求安全停止（不立即降落，保持悬停）"""
        self._running = False
        try:
            self.me.send_rc_control(0, 0, 0, 0)
        except Exception:
            pass

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _emit(self):
        """
        向外推送当前状态快照。推送字段：
            state          : 当前状态字符串
            rings_passed   : 已穿越数量
            total_rings    : 目标总数
            confirm_count  : 当前对准累计帧数
            confirm_target : 触发穿越所需帧数
            err_x          : 水平偏差（像素，正=偏右）
            err_y          : 垂直偏差（像素，正=偏下）
        """
        if self.status_callback:
            self.status_callback({
                'state':          self.state,
                'rings_passed':   self.rings_passed,
                'total_rings':    self.TOTAL_RINGS,
                'confirm_count':  self.confirm_count,
                'confirm_target': self.CONFIRM_FRAMES,
                'err_x':          int(self.err_x),
                'err_y':          int(self.err_y),
            })

    def _find_ring(self, img):
        """
        在图像中检测彩色圆环。
        流程：HSV 转换 → 颜色阈值 → 形态学降噪 → 轮廓筛选 → 取最大轮廓

        返回：
            (cx, cy) | None : 圆环中心坐标，未检测到时为 None
            area            : 轮廓面积
            mask            : 二值掩膜（调试用）
        """
        hsv  = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.HSV_LOWER, self.HSV_UPPER)

        # 开运算去除小噪点，闭运算填充轮廓孔洞
        k    = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, 0, mask

        biggest = max(contours, key=cv2.contourArea)
        area    = cv2.contourArea(biggest)
        if area < self.MIN_AREA:
            return None, 0, mask

        x, y, w, h = cv2.boundingRect(biggest)
        cx = x + w // 2
        cy = y + h // 2
        return (cx, cy), area, mask

    def _get_control(self, cx, cy):
        """
        根据圆环中心与图像中心的偏差计算 RC 控制量。
        与 detect_circle.py 中的 get_control() 完全一致：
          err_x > 0 → 圆环偏右 → lr 正（向右平移）
          err_y > 0 → 圆环偏下 → ud 负（向下修正），因此对 err_y 取反

        返回：(lr, ud, err_x, err_y)
        """
        err_x = cx - self.IMG_W // 2
        err_y = cy - self.IMG_H // 2
        lr    = int(np.clip( err_x * self.KP, -self.MAX_CTRL, self.MAX_CTRL))
        ud    = int(np.clip(-err_y * self.KP, -self.MAX_CTRL, self.MAX_CTRL))
        return lr, ud, err_x, err_y

    def _run(self):
        """
        主状态机循环（在独立线程中运行）。
        与 detect_circle.py 中的 while True 主循环逻辑完全一致，
        仅去除了 cv2.imshow 调用并改用 _emit() 推送状态。
        """
        state           = self.SEARCHING
        confirm_count   = 0
        lost_count      = 0
        rings_passed    = 0
        pass_start_time = None

        while self._running:
            # ─── 获取并预处理帧 ───────────────────────────────────────
            try:
                img = self.me.get_frame_read().frame
            except Exception:
                time.sleep(self.LOOP_DELAY)
                continue
            img = cv2.resize(img, (self.IMG_W, self.IMG_H))
            center, area, _ = self._find_ring(img)

            # ─────────── SEARCHING ────────────────────────────────────
            if state == self.SEARCHING:
                confirm_count = 0
                lost_count    = 0
                self.err_x    = 0
                self.err_y    = 0
                if center is not None:
                    # 发现圆环：停止旋转，切换到对准阶段
                    self.me.send_rc_control(0, 0, 0, 0)
                    state = self.CENTERING
                else:
                    # 未发现：偏航旋转搜索
                    self.me.send_rc_control(0, 0, 0, self.SEARCH_YAW)

            # ─────────── CENTERING ────────────────────────────────────
            elif state == self.CENTERING:
                if center is None:
                    # 短暂丢失：悬停等待，避免立即放弃
                    lost_count += 1
                    self.me.send_rc_control(0, 0, 0, 0)
                    if lost_count >= self.LOST_LIMIT:
                        state = self.SEARCHING
                else:
                    lost_count = 0
                    cx, cy = center
                    lr, ud, err_x, err_y = self._get_control(cx, cy)
                    self.err_x = err_x
                    self.err_y = err_y
                    is_centered = (abs(err_x) < self.CENTER_TOL and
                                   abs(err_y) < self.CENTER_TOL)

                    if is_centered:
                        # 偏差在容差内：悬停并累积对准帧计数
                        confirm_count += 1
                        self.me.send_rc_control(0, 0, 0, 0)
                    else:
                        # 偏差超限：比例控制修正，重置计数
                        confirm_count = 0
                        self.me.send_rc_control(lr, 0, ud, 0)

                    if confirm_count >= self.CONFIRM_FRAMES:
                        # 连续对准达标 → 开始穿越
                        pass_start_time = time.time()
                        state           = self.PASSING
                        confirm_count   = 0

            # ─────────── PASSING ─────────────────────────────────────
            elif state == self.PASSING:
                elapsed = time.time() - pass_start_time
                if elapsed < self.PASS_TIME:
                    # 全速前进穿越
                    self.me.send_rc_control(0, self.PASS_SPEED, 0, 0)
                else:
                    # 穿越完成：悬停稳定
                    self.me.send_rc_control(0, 0, 0, 0)
                    time.sleep(0.5)
                    rings_passed   += 1
                    confirm_count   = 0
                    lost_count      = 0
                    pass_start_time = None
                    state = (self.DONE
                             if rings_passed >= self.TOTAL_RINGS
                             else self.SEARCHING)

            # ─────────── DONE ────────────────────────────────────────
            elif state == self.DONE:
                self.me.land()
                self._running = False
                break

            # ─── 同步对外状态并推送 ───────────────────────────────────
            self.state         = state
            self.rings_passed  = rings_passed
            self.confirm_count = confirm_count
            self._emit()

            time.sleep(self.LOOP_DELAY)

        # ─── 退出时确保 RC 清零 ───────────────────────────────────────
        try:
            self.me.send_rc_control(0, 0, 0, 0)
        except Exception:
            pass
        self.state = self.IDLE
        self._emit()
