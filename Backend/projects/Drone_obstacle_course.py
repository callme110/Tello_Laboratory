"""
Drone_obstacle_course.py  ——  ObstacleTask 类
────────────────────────────────────────────────────────────
相较于原版的主要改进：

  1. 封装为 ObstacleTask 类，通过构造函数注入已连接的 Tello 实例，
     去除模块级 Tello 初始化、Tkinter GUI 和 cv2.imshow，
     可被 Flask 后端安全导入和多次启停。

  2. 放弃原版的 SimpleBlobDetector（面积范围 100~500 像素，对真实
     彩色障碍物几乎无效），改用 HSV 颜色阈值 + 轮廓检测，
     与 ring_task.py 保持一致的视觉处理风格，标定工具通用。

  3. 采用反应式避障策略（Reactive Avoidance）替换原版的离散
     move_forward/left/right 指令：
       - FORWARD  状态：持续缓速前进，每帧检测障碍物
       - AVOIDING 状态：检测到障碍物 → 计算质心 → 向空旷侧横移
                        持续 AVOID_TIME 秒后自动恢复 FORWARD
     全程使用 send_rc_control 连续下发，飞行更平滑。

  4. 支持双色段检测（默认针对红色障碍物，HSV 红色跨越 0° 和 180°
     需两段 inRange 取并集）。若障碍物为其他颜色，只需修改
     HSV_LOWER / HSV_UPPER，并将 USE_DUAL_RANGE 设为 False。

  5. 通过 status_callback 向 Flask/SocketIO 实时推送运行状态，
     前端可据此绘制障碍物检测可视化、偏移指示等。

  6. 提供 start() / stop() 接口，支持多次启停，线程以 daemon 模式运行。

参数标定提示：
  - 用 ColorPicker.py 对实际障碍物标定 HSV_LOWER / HSV_UPPER。
  - 若障碍物不是红色，将 USE_DUAL_RANGE 设为 False，
    只使用 HSV_LOWER / HSV_UPPER 单段。
  - MIN_OBSTACLE_RATIO 是触发避障的像素占比阈值，环境光线强时
    可适当调大（如 0.12），避免背景误触发。
  - FWD_SPEED 建议 15~25 cm/s，AVOID_SPEED 建议 25~35 cm/s。
"""

import cv2
import numpy as np
import threading
import time


class ObstacleTask:
    """
    反应式彩色障碍物避障任务。

    状态流转：
        IDLE ──start()──► FORWARD
                            │ 检测到障碍物（覆盖率 > MIN_OBSTACLE_RATIO）
                          AVOIDING ── 持续 AVOID_TIME 秒横移
                            │ 时间到
                          FORWARD（继续前进寻找下一个障碍物）
    """

    # ─── 颜色参数（用 ColorPicker.py 标定后修改）────────────────────────────
    # 默认值：红色障碍物（红色在 HSV 中跨越 0° 附近，需两段检测）
    HSV_LOWER  = np.array([0,   120, 100])   # 红色低段下限
    HSV_UPPER  = np.array([10,  255, 255])   # 红色低段上限
    HSV_LOWER2 = np.array([160, 120, 100])   # 红色高段下限
    HSV_UPPER2 = np.array([179, 255, 255])   # 红色高段上限
    USE_DUAL_RANGE = True                    # 红色等跨零色相需 True；橙/黄/绿设 False

    # ─── 图像参数 ────────────────────────────────────────────────────────────
    IMG_W     = 480     # 处理分辨率：宽（像素）
    IMG_H     = 360     # 处理分辨率：高（像素）
    ROI_Y_END = 270     # ROI 结束行（只看画面上方 3/4，忽略地面）
    MIN_AREA  = 400     # 最小有效轮廓面积（像素²），低于此视为噪声

    # ─── 避障触发参数 ────────────────────────────────────────────────────────
    # 障碍物有效像素 / ROI 总像素 超过此比例时触发避障
    MIN_OBSTACLE_RATIO = 0.08

    # ─── 飞行参数 ────────────────────────────────────────────────────────────
    FWD_SPEED  = 20     # 前进速度（cm/s），建议 15~25
    AVOID_SPEED = 30    # 避障横移速度（cm/s），建议 25~35
    AVOID_TIME = 0.8    # 每次避障横移持续时间（秒）
    LOOP_DELAY = 0.033  # 主循环延时（秒），约 30 fps

    # ─── 状态常量 ─────────────────────────────────────────────────────────────
    IDLE     = 'IDLE'
    FORWARD  = 'FORWARD'
    AVOIDING = 'AVOIDING'

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
        self.state          = self.IDLE
        self.obstacle_ratio = 0.0   # 当前帧障碍物像素占比
        self.obstacle_cx    = 0     # 障碍物质心 x（未检测到时为 0）
        self.avoid_dir      = 0     # 当前避障方向：正=向右，负=向左

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """
        启动避障任务（非阻塞，后台线程运行）。
        返回 False 表示任务已在运行中。
        调用前请确保 Tello 已 takeoff 并 streamon。
        """
        if self._running:
            return False
        self._running       = True
        self.state          = self.FORWARD
        self.obstacle_ratio = 0.0
        self.obstacle_cx    = 0
        self.avoid_dir      = 0
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        """外部请求安全停止（无人机悬停，不自动降落）"""
        self._running = False
        try:
            self.me.send_rc_control(0, 0, 0, 0)
        except Exception:
            pass

    # ── 内部方法 ──────────────────────────────────────────────────────────────

    def _emit(self):
        """
        向外推送当前状态快照。推送字段：
            state           : 当前状态字符串（IDLE / FORWARD / AVOIDING）
            obstacle_ratio  : 当前帧障碍物像素占比（0.0~1.0）
            obstacle_cx     : 障碍物质心 x（像素），未检测到时为 0
            avoid_dir       : 避障方向（正=向右横移，负=向左横移，0=未避障）
            img_w           : 图像宽度（前端绘制位置参考）
        """
        if self.status_callback:
            self.status_callback({
                'state':          self.state,
                'obstacle_ratio': round(self.obstacle_ratio, 4),
                'obstacle_cx':    int(self.obstacle_cx),
                'avoid_dir':      int(self.avoid_dir),
                'img_w':          self.IMG_W,
            })

    def _detect_obstacle(self, img):
        """
        在图像 ROI（上方 3/4）中检测彩色障碍物。

        流程：缩放 → 截取 ROI → HSV 阈值（支持双色段）→
              形态学降噪 → 轮廓筛选 → 计算质心与覆盖率

        返回：
            cx    : 最大轮廓质心 x（像素），未检测到时为 None
            ratio : 有效白色像素 / ROI 总像素
            mask  : ROI 区域的二值掩膜
        """
        img = cv2.resize(img, (self.IMG_W, self.IMG_H))
        roi = img[:self.ROI_Y_END, :]

        hsv  = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.HSV_LOWER, self.HSV_UPPER)

        if self.USE_DUAL_RANGE:
            mask2 = cv2.inRange(hsv, self.HSV_LOWER2, self.HSV_UPPER2)
            mask  = cv2.bitwise_or(mask, mask2)

        # 形态学：开运算去小噪点，闭运算填孔洞
        k    = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

        # 障碍物像素占比（用于判断触发阈值）
        roi_pixels = roi.shape[0] * roi.shape[1]
        white      = cv2.countNonZero(mask)
        ratio      = white / roi_pixels if roi_pixels > 0 else 0.0

        # 找最大轮廓，用 moments 定质心
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, ratio, mask

        biggest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(biggest) < self.MIN_AREA:
            return None, ratio, mask

        M = cv2.moments(biggest)
        if M['m00'] == 0:
            return None, ratio, mask

        cx = int(M['m10'] / M['m00'])
        return cx, ratio, mask

    def _choose_avoid_dir(self, cx):
        """
        根据障碍物质心决定横移方向。

        策略：障碍物质心在图像左半 → 向右横移绕过（avoid_dir 正）
              障碍物质心在图像右半 → 向左横移绕过（avoid_dir 负）

        返回：±AVOID_SPEED
        """
        if cx < self.IMG_W // 2:
            return self.AVOID_SPEED    # 障碍物偏左，向右绕
        else:
            return -self.AVOID_SPEED   # 障碍物偏右，向左绕

    def _run(self):
        """
        主避障循环（在独立线程中运行）。

        FORWARD  状态：缓速前进，持续检测障碍物。
        AVOIDING 状态：向空旷侧横移 AVOID_TIME 秒，然后恢复 FORWARD。
        """
        state           = self.FORWARD
        avoid_start     = None
        current_avoid_lr = 0

        while self._running:

            # ─── 获取并预处理帧 ───────────────────────────────────────
            try:
                raw = self.me.get_frame_read().frame
            except Exception:
                time.sleep(self.LOOP_DELAY)
                continue

            cx, ratio, _ = self._detect_obstacle(raw)

            # ─── FORWARD ─────────────────────────────────────────────
            if state == self.FORWARD:
                self.obstacle_ratio = ratio
                self.obstacle_cx    = cx if cx is not None else 0
                self.avoid_dir      = 0

                if ratio >= self.MIN_OBSTACLE_RATIO and cx is not None:
                    # 检测到障碍物：停止前进，决定横移方向，进入 AVOIDING
                    current_avoid_lr = self._choose_avoid_dir(cx)
                    avoid_start      = time.time()
                    state            = self.AVOIDING
                    self.avoid_dir   = current_avoid_lr
                    self.me.send_rc_control(current_avoid_lr, 0, 0, 0)
                else:
                    # 无障碍：匀速前进
                    self.me.send_rc_control(0, self.FWD_SPEED, 0, 0)

            # ─── AVOIDING ────────────────────────────────────────────
            elif state == self.AVOIDING:
                elapsed = time.time() - avoid_start
                if elapsed < self.AVOID_TIME:
                    # 持续横移，不更新方向（避免中途被对侧检测干扰）
                    self.me.send_rc_control(current_avoid_lr, 0, 0, 0)
                else:
                    # 避障完成：悬停 0.3 秒稳定，恢复前进
                    self.me.send_rc_control(0, 0, 0, 0)
                    time.sleep(0.3)
                    avoid_start      = None
                    current_avoid_lr = 0
                    state            = self.FORWARD

                self.obstacle_ratio = ratio
                self.obstacle_cx    = cx if cx is not None else 0

            # ─── 同步对外状态并推送 ───────────────────────────────────
            self.state = state
            self._emit()

            time.sleep(self.LOOP_DELAY)

        # ─── 退出时清零 RC ────────────────────────────────────────────
        try:
            self.me.send_rc_control(0, 0, 0, 0)
        except Exception:
            pass
        self.state = self.IDLE
        self._emit()
