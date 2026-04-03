# Tello 无人机控制系统

基于 DJI Tello 无人机的前后端一体化控制平台。Python 后端通过 Flask + SocketIO 提供 REST API 与实时 WebSocket 推送；React 前端提供可视化控制界面，支持键盘操控、穿环、巡线、降落等任务。

---

## 快速开始

### 1. 硬件准备

1. 启动 Tello 无人机，等待指示灯缓慢闪烁（就绪状态）
2. 电脑连接 Tello Wi-Fi 热点（SSID：`TELLO-XXXXXX`，无密码）

### 2. 安装 uv

推荐使用 [uv](https://github.com/astral-sh/uv) 管理 Python 环境，速度比 pip 快约 10–100 倍，并内置虚拟环境管理。

```bash
# Windows（PowerShell）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装后验证：
```bash
uv --version
```

### 3. 配置 Python 环境

```bash
# 在项目根目录执行
uv venv                              # 创建 .venv 虚拟环境
uv pip install -r requirements.txt  # 安装后端所有依赖
```

激活虚拟环境（切换终端后需要重新激活）：

| 平台 | 激活命令 |
|------|---------|
| Windows CMD | `.venv\Scripts\activate` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| macOS / Linux | `source .venv/bin/activate` |

> 也可跳过激活，直接用 `uv run python <脚本>` 运行，uv 会自动使用 `.venv`。

### 4. 前端依赖

```bash
cd Frontend
pnpm install        # 若未安装 pnpm：npm install -g pnpm
```

### 5. 启动服务

```bash
# 终端 1 — 后端（端口 5000，需先激活 .venv 或使用 uv run）
cd Frontend
uv run python backend_example.py dev

# 终端 2 — 前端（端口 5173）
cd Frontend
pnpm dev
```

浏览器访问 **http://localhost:5173**，点击「检测连接」即可开始使用。

---

## 环境管理（uv）参考

本节列出 uv 的常用操作，供日常开发参考。完整快速开始流程见 [§ 快速开始](#快速开始)。

### 虚拟环境操作

| 操作 | 命令 |
|------|------|
| 创建虚拟环境（`.venv/`） | `uv venv` |
| 指定 Python 版本创建 | `uv venv --python 3.11` |
| 激活环境（Windows CMD） | `.venv\Scripts\activate` |
| 激活环境（Windows PowerShell） | `.venv\Scripts\Activate.ps1` |
| 激活环境（macOS / Linux） | `source .venv/bin/activate` |
| 退出虚拟环境 | `deactivate` |

---

### 依赖管理

```bash
# 安装 requirements.txt 中的全部依赖
uv pip install -r requirements.txt

# 安装单个包
uv pip install <package>

# 卸载包
uv pip uninstall <package>

# 查看已安装的包
uv pip list

# 将当前环境依赖导出为 requirements.txt
uv pip freeze > requirements.txt
```

---

### 直接运行脚本（无需手动激活环境）

```bash
# 运行后端
uv run python Frontend/backend_example.py dev

# 运行颜色标定工具
uv run python Backend/vision/ColorPicker.py
```

---

## 界面功能说明

### 连接与电量

| 操作 | 说明 |
|------|------|
| 检测连接 | 连接 Tello 并读取当前电量，连接成功后自动建立 WebSocket |
| 电量条 | 实时显示电池电量百分比 |

> 所有功能（穿环、巡线、键盘控制）均需先连接成功。

---

### 键盘控制

连接成功后，键盘即可实时控制无人机（通过 WebSocket 持续下发 RC 指令）：

| 按键 | 动作 |
|------|------|
| `↑ ↓ ← →` | 前 / 后 / 左 / 右平移 |
| `W` / `S` | 上升 / 下降 |
| `A` / `D` | 左转偏航 / 右转偏航 |
| `E` | 起飞 |
| `Q` | 降落 |

界面上的四个方向箭头按钮支持鼠标点按与触屏长按，效果与键盘一致。

> **起飞前提：** 确保周围无障碍物，天花板高度 > 1.5 m。

---

### 穿环任务

1. 无人机起飞后，点击「**穿环**」按钮启动任务
2. 状态面板实时显示当前阶段与进度：

| 状态 | 含义 |
|------|------|
| 搜索圆环 | 无人机旋转搜索橙色圆环 |
| 对准中 | 检测到圆环，比例控制修正 X/Y 偏差 |
| 穿越中 | 连续对准 20 帧后全速前进穿越 |
| 已完成 | 三个圆环全部穿越，自动降落 |

3. 任意时刻点击「**停止任务**」可安全悬停

**参数标定（首次使用必做）：**
```bash
cd Backend/vision
python ColorPicker.py    # 对准实际圆环，记录 HSV 范围
```
将结果填入 `Backend/projects/ring_task.py` 的 `HSV_LOWER` / `HSV_UPPER`。

---

### 巡线任务

1. 安装反射镜（3D 打印件位于 `Resource/files/`），使摄像头朝向地面
2. 无人机起飞后，点击「**巡线**」按钮启动任务
3. 状态面板实时显示：

| 显示元素 | 含义 |
|----------|------|
| 左 / 中 / 右 传感器 | 青色高亮表示该区域检测到赛道 |
| 横向偏差条 | 线偏左显示绿色（< 10% 宽度），偏差大转为黄色 |
| 偏航 / 平移 | 实时 PD 控制输出值 |
| 线丢失 | 超过 30 帧未检测到赛道，任务自动停止并悬停 |

4. 点击「**停止巡线**」可安全悬停

**参数标定：**
```bash
python ColorPicker.py    # 标定赛道颜色（默认针对黑色线）
```
将结果填入 `Backend/projects/LineFollower.py` 的 `HSV_LOWER` / `HSV_UPPER`。

**PD 参数调整（`LineFollower.py`）：**

| 参数 | 默认值 | 调整方向 |
|------|--------|---------|
| `KP_YAW` | 0.20 | 蛇形抖动 → 调小；反应迟缓 → 调大 |
| `KD_YAW` | 0.05 | 转弯超调 → 调大 |
| `FWD_SPEED` | 15 | 速度（cm/s），建议 10~20 |

---

### 降落

点击「**降落**」按钮，无人机立即执行降落指令（等效于键盘 `Q`）。

---

### 避障任务

1. 无人机起飞后，点击「**避障**」按钮启动任务
2. 状态面板实时显示当前阶段与检测信息：

| 状态 | 含义 |
|------|------|
| 前进中 | 缓速前进（20 cm/s），每帧检测前方障碍物 |
| 绕障中 | 检测到障碍物，向空旷侧横移 0.8 秒后恢复前进 |

- **覆盖率**：障碍物在画面中的像素占比，超过 8% 时触发绕障
- **障碍物位置条**：橙色圆点指示质心位置；质心偏左→向右绕行，质心偏右→向左绕行

3. 点击「**停止避障**」可随时安全悬停

**避障原理（反应式策略）：**
- 使用 HSV 颜色阈值识别障碍物（默认针对红色，支持双色段检测）
- 全程 `send_rc_control` 连续下发指令，飞行平滑无跳变
- 与穿环 / 巡线使用同一套颜色标定工具

**参数标定（首次使用必做）：**
```bash
cd Backend/vision
python ColorPicker.py    # 标定障碍物颜色（默认针对红色障碍物）
```
将结果填入 `Backend/projects/Drone_obstacle_course.py` 的 `HSV_LOWER` / `HSV_UPPER`。

若障碍物为**非红色**（橙、黄、绿等），同时将 `USE_DUAL_RANGE` 设为 `False`。

**关键参数调整（`Drone_obstacle_course.py`）：**

| 参数 | 默认值 | 调整方向 |
|------|--------|---------|
| `MIN_OBSTACLE_RATIO` | 0.08 | 误触发频繁 → 调大；检测不灵敏 → 调小 |
| `FWD_SPEED` | 20 | 前进速度（cm/s），建议 15~25 |
| `AVOID_SPEED` | 30 | 横移速度（cm/s），建议 25~35 |
| `AVOID_TIME` | 0.8 | 每次横移持续时间（秒），障碍物较宽时调大 |

---

## 后端 API 一览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/tello/connect` | GET | 连接无人机，返回电量 |
| `/api/tello/status` | GET | 查询连接状态与电量（轮询用） |
| `/api/tello/takeoff` | POST | 起飞 |
| `/api/tello/land` | POST | 降落 |
| `/api/tello/direction/<dir>` | POST | 单步移动：上/下/左/右（20 cm） |
| `/api/tello/ring/start` | POST | 启动穿环任务 |
| `/api/tello/ring/stop` | POST | 停止穿环任务 |
| `/api/tello/line/start` | POST | 启动巡线任务 |
| `/api/tello/line/stop` | POST | 停止巡线任务 |
| `/api/tello/obstacle/start` | POST | 启动避障任务 |
| `/api/tello/obstacle/stop` | POST | 停止避障任务 |

**WebSocket 事件（服务端 → 客户端）：**

| 事件名 | 触发时机 | 数据字段 |
|--------|---------|---------|
| `ring_status` | 穿环任务每帧 | `state, rings_passed, total_rings, confirm_count, confirm_target, err_x, err_y` |
| `line_status` | 巡线任务每帧 | `state, cx, err, yaw, lr, sensors, lost_count, img_w` |
| `obstacle_status` | 避障任务每帧 | `state, obstacle_ratio, obstacle_cx, avoid_dir, img_w` |

**WebSocket 事件（客户端 → 服务端）：**

| 事件名 | 触发时机 | 数据字段 |
|--------|---------|---------|
| `key_down` | 键盘/按钮按下 | `{ key: string }` |
| `key_up` | 键盘/按钮松开 | `{ key: string }` |

---

## 项目结构

```
Tello_Course/
├── Backend/
│   ├── basic/              # 基础飞行示例脚本
│   ├── control/            # 键盘控制（单机版）
│   ├── vision/             # 视觉工具（人脸追踪、颜色标定）
│   └── projects/
│       ├── ring_task.py    # 穿环任务类（RingTask）
│       ├── LineFollower.py # 巡线任务类（LineTask，PD 控制器）
│       ├── Drone_obstacle_course.py  # 避障任务类（ObstacleTask，反应式避障）
│       └── detect_circle.py / mapping.py / ...  # 参考脚本
│
├── Frontend/
│   ├── backend_example.py  # Flask + SocketIO 后端（主入口）
│   └── src/app/App.tsx     # React 主界面
│
├── Resource/
│   ├── haarcascade_frontalface_default.xml
│   └── files/              # 反射镜 3D 打印模型（STL）
│
├── Docs/
│   ├── 环境配置指南.md     # 详细环境搭建说明
│   └── CV2笔记--图像处理.pdf
│
└── README.md               # 本文件
```

---

## 安全须知

- 首次使用在 **空旷室内** 测试，确保周围 2 m 内无障碍物
- 电量低于 **20%** 时立即点击「降落」或按 `Q`
- 穿环 / 巡线任务运行期间，保持手指随时可按「停止」
- Tello 飞行上限约 **8 分钟**，注意控制单次飞行时间

---

## 参考资料

- [djitellopy 文档](https://github.com/damiafuentes/DJITelloPy)
- [Tello SDK 2.0](https://dl-cdn.ryzerobotics.com/downloads/Tello/Tello%20SDK%202.0%20User%20Guide.pdf)
- [OpenCV 官网](https://opencv.org/)
- [Flask-SocketIO 文档](https://flask-socketio.readthedocs.io/)
- 反射镜 3D 模型：[Thingiverse #2911427](https://www.thingiverse.com/thing:2911427)
