"""
LineFollower.py  ——  LineTask 类
────────────────────────────────────────────────────────────
相较于原版的主要改进：

  1. 封装为 LineTask 类，通过构造函数注入已连接的 Tello 实例，
     去除模块级初始化（原版 me = tello.Tello() / me.connect()），
     使其可被 Flask 等后端框架安全导入。

  2. 改用 PD 控制器（比例 + 微分）替换原版 5 档固定偏航权重表，
     消除因权重跳变引起的蛇形抖动，调节更平滑。
       yaw = Kp * err + Kd * Δerr
     lr 轴同理用 P 控制替换原版的简单阈值截断。

  3. 改用 cv2.moments 质心替换 cv2.boundingRect 矩形中心，
     对非矩形、弯曲赛道的中心估计更准确。

  4. 引入 ROI（Region Of Interest）：只处理画面下方 2/3，
     减少前景干扰，降低计算量。

  5. 去除所有 cv2.imshow / cv2.waitKey 调用，适合无 GUI 后台线程。

  6. 通过 status_callback 向 Flask/SocketIO 实时推送运行状态，
     前端可据此绘制传感器可视化、偏差计等。

  7. 提供 start() / stop() 接口，支持多次启停，线程以 daemon 模式运行。

  8. flip_vertical 参数支持使用反射镜安装时的图像垂直翻转。

参数标定提示：
  - 用 ColorPicker.py 对实际赛道标定 HSV_LOWER / HSV_UPPER（默认针对黑色线）
  - 在空旷场地先测试 KP_YAW / KD_YAW，若蛇形严重降低 KP_YAW；
    若反应迟钝提高 KP_YAW。
  - FWD_SPEED 建议 10~20 cm/s（值越小越安全）。
"""

import cv2
import numpy as np
import threading
import time


class LineTask:
    """
    地面赛道巡线任务（PD 控制器）。

    状态流转：
        IDLE ──start()──► FOLLOWING
                            │ 连续 LOST_LIMIT 帧未检测到赛道
                          LOST ──► 悬停并停止任务 ──► IDLE
    """

    # ─── 颜色参数（用 ColorPicker.py 标定后修改）────────────────────────────
    # 默认值：黑色赛道（低饱和度、低亮度）
    HSV_LOWER = np.array([0,   0,   0  ])
    HSV_UPPER = np.array([179, 50,  80 ])

    # ─── 图像参数 ────────────────────────────────────────────────────────────
    IMG_W         = 480     # 处理分辨率：宽（像素）
    IMG_H         = 360     # 处理分辨率：高（像素）
    ROI_Y_START   = 120     # ROI 起始行（IMG_H // 3），只处理下方 2/3 区域
    SENSORS       = 3       # 虚拟传感器数量（左 / 中 / 右）
    THRESHOLD     = 0.20    # 传感器有效激活阈值（白色像素占比 > 20%）
    MIN_AREA      = 500     # 最小有效轮廓面积（像素²），低于此视为噪声

    # ─── PD 控制参数 ─────────────────────────────────────────────────────────
    KP_YAW  = 0.20      # 偏航比例系数
    KD_YAW  = 0.05      # 偏航微分系数（抑制超调）
    KP_LR   = 0.10      # 左右平移比例系数（辅助修正横向偏差）
    MAX_YAW = 30        # 偏航控制量上限（cm/s）
    MAX_LR  = 15        # 左右平移控制量上限（cm/s）

    # ─── 飞行参数 ────────────────────────────────────────────────────────────
    FWD_SPEED  = 15     # 前进速度（cm/s），建议 10~20
    LOST_LIMIT = 30     # 连续丢失帧数上限，超过后停止任务（约 1 秒）
    LOOP_DELAY = 0.033  # 主循环延时（秒），约 30 fps

    # ─── 状态常量 ─────────────────────────────────────────────────────────────
    IDLE      = 'IDLE'
    FOLLOWING = 'FOLLOWING'
    LOST      = 'LOST'

    def __init__(self, tello_obj, status_callback=None, flip_vertical: bool = True):
        """
        参数：
            tello_obj       : 已连接（且已 streamon）的 djitellopy.Tello 实例
            status_callback : func(dict) → 每次状态更新时调用，用于 WebSocket 推送
                              dict 字段见 _emit() 方法注释
            flip_vertical   : 是否垂直翻转图像（使用反射镜安装时需要 True）
        """
        self.me              = tello_obj
        self.status_callback = status_callback
        self.flip_vertical   = flip_vertical
        self._running        = False
        self._thread: threading.Thread | None = None

        # ─── 对外只读的实时状态 ───
        self.state      = self.IDLE
        self.cx         = self.IMG_W // 2   # 检测到的线中心 x 坐标
        self.err        = 0                 # 当前偏差（正=偏右）
        self.yaw        = 0                 # 当前偏航控制量
        self.lr         = 0                 # 当前左右平移控制量
        self.sensors    = [0, 0, 0]         # 3 个虚拟传感器输出
        self.lost_count = 0

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """
        启动巡线任务（非阻塞，后台线程运行）。
        返回 False 表示任务已在运行中。
        调用前请确保 Tello 已 takeoff 并 streamon。
        """
        if self._running:
            return False
        self._running   = True
        self.state      = self.FOLLOWING
        self.lost_count = 0
        self.err        = 0
        self._prev_err  = 0     # PD 微分项暂存
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
            state       : 当前状态字符串（IDLE / FOLLOWING / LOST）
            cx          : 检测到的赛道中心 x（像素）
            err         : 当前偏差（像素，正=线偏右）
            yaw         : 发出的偏航控制量（cm/s）
            lr          : 发出的左右平移控制量（cm/s）
            sensors     : 3 元素列表，如 [0,1,0]
            lost_count  : 当前连续丢失帧数
            img_w       : 图像宽度（前端绘制偏差比例用）
        """
        if self.status_callback:
            self.status_callback({
                'state':      self.state,
                'cx':         int(self.cx),
                'err':        int(self.err),
                'yaw':        int(self.yaw),
                'lr':         int(self.lr),
                'sensors':    list(self.sensors),
                'lost_count': self.lost_count,
                'img_w':      self.IMG_W,
            })

    def _preprocess(self, img):
        """
        图像预处理：缩放 → （可选）垂直翻转 → 裁剪 ROI → HSV 阈值 → 形态学降噪。

        返回：
            roi_thres : ROI 区域的二值掩膜
            roi       : ROI 区域的原始彩色图（调试备用）
        """
        img = cv2.resize(img, (self.IMG_W, self.IMG_H))
        if self.flip_vertical:
            img = cv2.flip(img, 0)

        # 截取 ROI：只保留画面下方 2/3
        roi = img[self.ROI_Y_START:, :]

        hsv  = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self.HSV_LOWER, self.HSV_UPPER)

        # 形态学：开运算去噪点，闭运算填孔
        k    = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

        return mask, roi

    def _get_line_center(self, roi_thres):
        """
        用 moments 质心定位赛道中心 x 坐标。
        相比 boundingRect 对弯道、非矩形赛道更准确。

        返回：
            cx  : 赛道中心 x（像素），未检测到时返回 None
            area: 最大轮廓面积
        """
        contours, _ = cv2.findContours(roi_thres, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, 0

        biggest = max(contours, key=cv2.contourArea)
        area    = cv2.contourArea(biggest)
        if area < self.MIN_AREA:
            return None, 0

        M  = cv2.moments(biggest)
        if M['m00'] == 0:
            return None, 0

        cx = int(M['m10'] / M['m00'])
        return cx, area

    def _get_sensors(self, roi_thres):
        """
        将 ROI 水平三等分，统计各区域白色占比，输出 [L, C, R] 传感器信号。
        与原版 getSensorOutput 逻辑一致，但修复了引用外层 img 的 bug，
        并去除 cv2.imshow。

        返回：
            [int, int, int]  例如 [0, 1, 0]
        """
        strips   = np.hsplit(roi_thres, self.SENSORS)
        h, w_roi = roi_thres.shape[:2]
        total    = (w_roi // self.SENSORS) * h    # 每个条带的总像素数
        result   = []
        for strip in strips:
            white = cv2.countNonZero(strip)
            result.append(1 if white > self.THRESHOLD * total else 0)
        return result

    def _pd_control(self, cx):
        """
        PD 控制器：根据质心偏差计算偏航量（yaw）和左右平移量（lr）。

        偏差定义：
          err = cx - IMG_W/2
          err > 0  →  赛道中心在图像右侧  →  无人机需向右偏航（yaw 正）
          err < 0  →  赛道中心在图像左侧  →  无人机需向左偏航（yaw 负）

        PD 公式：
          yaw = KP_YAW * err + KD_YAW * (err - prev_err)

        辅助 lr 平移（小增益，减少纯偏航导致的横移误差积累）：
          lr  = KP_LR  * err

        返回：(yaw, lr, err)
        """
        err       = cx - self.IMG_W // 2
        d_err     = err - self._prev_err
        self._prev_err = err

        yaw = int(np.clip(self.KP_YAW * err + self.KD_YAW * d_err,
                          -self.MAX_YAW, self.MAX_YAW))
        lr  = int(np.clip(self.KP_LR  * err, -self.MAX_LR,  self.MAX_LR))

        return yaw, lr, err

    def _run(self):
        """
        主巡线循环（在独立线程中运行）。

        FOLLOWING 状态：持续检测赛道并发送 RC 指令。
        LOST      状态：连续丢失超过 LOST_LIMIT 帧后悬停并退出。
        """
        self._prev_err = 0
        state      = self.FOLLOWING
        lost_count = 0

        while self._running:

            # ─── 获取并预处理帧 ───────────────────────────────────────
            try:
                raw = self.me.get_frame_read().frame
            except Exception:
                time.sleep(self.LOOP_DELAY)
                continue

            roi_thres, _ = self._preprocess(raw)

            # ─── 检测赛道中心 ─────────────────────────────────────────
            cx, area = self._get_line_center(roi_thres)
            sensors  = self._get_sensors(roi_thres)

            # ─── FOLLOWING ────────────────────────────────────────────
            if state == self.FOLLOWING:
                if cx is not None:
                    lost_count = 0
                    yaw, lr, err = self._pd_control(cx)

                    # 发送：前进 + PD 偏航修正 + 辅助横移
                    self.me.send_rc_control(lr, self.FWD_SPEED, 0, yaw)

                    # 更新对外状态
                    self.cx      = cx
                    self.err     = err
                    self.yaw     = yaw
                    self.lr      = lr
                    self.sensors = sensors

                else:
                    # 短暂丢失：悬停等待
                    lost_count += 1
                    self.me.send_rc_control(0, 0, 0, 0)

                    if lost_count >= self.LOST_LIMIT:
                        state = self.LOST

            # ─── LOST ────────────────────────────────────────────────
            elif state == self.LOST:
                self.me.send_rc_control(0, 0, 0, 0)
                self._running = False
                break

            # ─── 同步对外状态并推送 ───────────────────────────────────
            self.state      = state
            self.lost_count = lost_count
            self._emit()

            time.sleep(self.LOOP_DELAY)

        # ─── 退出时清零 RC ────────────────────────────────────────────
        try:
            self.me.send_rc_control(0, 0, 0, 0)
        except Exception:
            pass
        self.state = self.IDLE
        self._emit()
