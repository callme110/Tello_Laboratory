# Tello 无人机控制后端
# 需要安装的库：
# pip install flask flask-cors flask-socketio djitellopy pywebview

import os
import sys

# 将 Backend/projects 加入 Python 路径，以便导入 ring_task
_PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             '..', 'Backend', 'projects')
sys.path.insert(0, _PROJECTS_DIR)
from ring_task import RingTask                          # noqa: E402
from LineFollower import LineTask                       # noqa: E402
from Drone_obstacle_course import ObstacleTask          # noqa: E402

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO
from djitellopy import Tello
import threading
import time

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# ── 连接状态 ─────────────────────────────────────────────────
tello: Tello | None = None
is_connected = False

# ── 穿环任务实例 ─────────────────────────────────────────────
ring_task: RingTask | None = None

# ── 巡线任务实例 ─────────────────────────────────────────────
line_task: LineTask | None = None

# ── 避障任务实例 ─────────────────────────────────────────────
obstacle_task: ObstacleTask | None = None

# ── RC 控制状态（对应 KeyboardControl.py 的 lr/fb/ud/yv）────
rc_state = {'lr': 0, 'fb': 0, 'ud': 0, 'yv': 0}
rc_lock   = threading.Lock()
rc_running = False

# 浏览器 key.key 名称 → (轴, 速度值)
# 与原 KeyboardControl.py 中的按键含义一致
KEY_AXIS_MAP: dict[str, tuple[str, int]] = {
    'ArrowLeft':  ('lr', -50),   # 左移
    'ArrowRight': ('lr',  50),   # 右移
    'ArrowUp':    ('fb',  50),   # 前进
    'ArrowDown':  ('fb', -50),   # 后退
    'w':          ('ud',  50),   # 上升
    's':          ('ud', -50),   # 下降
    'a':          ('yv', -50),   # 左转（偏航）
    'd':          ('yv',  50),   # 右转（偏航）
}


def rc_control_loop():
    """
    50 ms 循环持续下发 RC 指令，与原 KeyboardControl.py 的 while 循环等价。
    只要 rc_running 为 True 且无人机已连接，就持续调用 send_rc_control。
    """
    global rc_running
    rc_running = True
    while rc_running:
        if is_connected and tello is not None:
            with rc_lock:
                lr = rc_state['lr']
                fb = rc_state['fb']
                ud = rc_state['ud']
                yv = rc_state['yv']
            try:
                tello.send_rc_control(lr, fb, ud, yv)
            except Exception:
                pass
        time.sleep(0.05)


# ── WebSocket 事件处理 ────────────────────────────────────────

@socketio.on('key_down')
def on_key_down(data):
    """
    前端按键按下 → 设置对应轴速度。
    e / q 触发起飞 / 降落（放独立线程，避免阻塞 socket 线程）。
    """
    key = data.get('key', '')
    if key in KEY_AXIS_MAP:
        axis, val = KEY_AXIS_MAP[key]
        with rc_lock:
            rc_state[axis] = val
    elif key == 'e' and is_connected and tello is not None:
        threading.Thread(target=tello.takeoff, daemon=True).start()
    elif key == 'q' and is_connected and tello is not None:
        threading.Thread(target=tello.land, daemon=True).start()


@socketio.on('key_up')
def on_key_up(data):
    """前端按键松开 → 对应轴速度归零，停止该方向运动"""
    key = data.get('key', '')
    if key in KEY_AXIS_MAP:
        axis, _ = KEY_AXIS_MAP[key]
        with rc_lock:
            rc_state[axis] = 0


@app.route('/api/tello/connect', methods=['GET'])
def connect_tello():
    """
    连接 Tello 无人机并返回电量。
    若已连接则直接返回当前电量，不重复建立连接。
    """
    global tello, is_connected

    # 已连接时直接刷新电量返回
    if is_connected and tello is not None:
        try:
            battery = tello.get_battery()
            return jsonify({
                'success': True,
                'connected': True,
                'battery': battery,
                'message': '已连接，电量已刷新'
            })
        except Exception as e:
            # 连接意外断开，重置状态
            is_connected = False
            tello = None

    # 建立新连接
    try:
        tello = Tello()
        tello.connect()
        battery = tello.get_battery()
        is_connected = True
        # 首次连接时启动 RC 控制循环
        if not rc_running:
            threading.Thread(target=rc_control_loop, daemon=True).start()
        return jsonify({
            'success': True,
            'connected': True,
            'battery': battery,
            'message': '连接成功'
        })
    except Exception as e:
        tello = None
        is_connected = False
        return jsonify({
            'success': False,
            'connected': False,
            'battery': 0,
            'message': f'连接失败：{str(e)}'
        }), 500


@app.route('/api/tello/status', methods=['GET'])
def get_status():
    """查询当前连接状态与电量（前端轮询用）"""
    global tello, is_connected
    if not is_connected or tello is None:
        return jsonify({
            'success': True,
            'connected': False,
            'battery': 0,
            'message': '未连接'
        })
    try:
        battery = tello.get_battery()
        return jsonify({
            'success': True,
            'connected': True,
            'battery': battery,
            'message': '连接正常'
        })
    except Exception as e:
        is_connected = False
        tello = None
        return jsonify({
            'success': False,
            'connected': False,
            'battery': 0,
            'message': f'状态异常：{str(e)}'
        }), 500


@app.route('/api/tello/battery', methods=['GET'])
def get_battery():
    """单独获取电池电量"""
    global tello, is_connected
    if not is_connected or tello is None:
        return jsonify({'success': False, 'message': '未连接'}), 400
    try:
        battery = tello.get_battery()
        return jsonify({'success': True, 'battery': battery})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/tello/function/<func_name>', methods=['POST'])
def execute_function(func_name):
    """执行无人机功能：穿环、巡线、避障、降落"""
    global tello, is_connected
    if not is_connected or tello is None:
        return jsonify({'success': False, 'message': '未连接'}), 400

    try:
        if func_name == '穿环':
            # 实现穿环逻辑
            # 这里需要根据你的具体算法实现
            # 例如：使用图像识别找到圆环，然后控制飞行穿过
            return jsonify({'success': True, 'message': '开始执行穿环任务'})

        elif func_name == '巡线':
            # 实现巡线逻辑
            # 使用摄像头识别线条，控制无人机沿线飞行
            return jsonify({'success': True, 'message': '开始执行巡线任务'})

        elif func_name == '避障':
            # 实现避障逻辑
            # 开启避障传感器，自动躲避障碍物
            return jsonify({'success': True, 'message': '开始执行避障任务'})

        elif func_name == '降落':
            # 降落
            tello.land()
            return jsonify({'success': True, 'message': '无人机正在降落'})

        else:
            return jsonify({'success': False, 'message': '未知功能'}), 400

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'执行失败: {str(e)}'
        }), 500

@app.route('/api/tello/direction/<direction>', methods=['POST'])
def control_direction(direction):
    """控制无人机方向：上、下、左、右"""
    global tello, is_connected
    if not is_connected or tello is None:
        return jsonify({'success': False, 'message': '未连接'}), 400

    try:
        distance = 20  # 移动距离（厘米）

        if direction == '上':
            tello.move_up(distance)
        elif direction == '下':
            tello.move_down(distance)
        elif direction == '左':
            tello.move_left(distance)
        elif direction == '右':
            tello.move_right(distance)
        else:
            return jsonify({'success': False, 'message': '未知方向'}), 400

        return jsonify({
            'success': True,
            'message': f'向{direction}移动{distance}cm'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'移动失败: {str(e)}'
        }), 500

@app.route('/api/tello/takeoff', methods=['POST'])
def takeoff():
    """起飞"""
    global tello, is_connected
    if not is_connected or tello is None:
        return jsonify({'success': False, 'message': '未连接'}), 400

    try:
        tello.takeoff()
        return jsonify({'success': True, 'message': '起飞成功'})
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'起飞失败: {str(e)}'
        }), 500


@app.route('/api/tello/land', methods=['POST'])
def land():
    """降落"""
    global tello, is_connected
    if not is_connected or tello is None:
        return jsonify({'success': False, 'message': '未连接'}), 400

    try:
        threading.Thread(target=tello.land, daemon=True).start()
        return jsonify({'success': True, 'message': '无人机正在降落'})
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'降落失败: {str(e)}'
        }), 500


# ── 穿环任务端点 ──────────────────────────────────────────────

@app.route('/api/tello/ring/start', methods=['POST'])
def ring_start():
    """
    启动穿环任务。
    前置条件：无人机已连接（/api/tello/connect）且已起飞。
    任务运行期间，通过 WebSocket 事件 'ring_status' 向前端推送实时进度。
    """
    global tello, is_connected, ring_task

    if not is_connected or tello is None:
        return jsonify({'success': False, 'message': '无人机未连接'}), 400

    if ring_task is not None and ring_task.is_running:
        return jsonify({'success': False, 'message': '穿环任务已在运行中'}), 400

    def on_status(data):
        """状态回调：通过 SocketIO 实时广播给前端"""
        socketio.emit('ring_status', data)

    ring_task = RingTask(tello, status_callback=on_status)
    ring_task.start()

    return jsonify({'success': True, 'message': '穿环任务已启动'})


@app.route('/api/tello/ring/stop', methods=['POST'])
def ring_stop():
    """安全停止穿环任务（无人机悬停，不自动降落）"""
    global ring_task

    if ring_task is None or not ring_task.is_running:
        return jsonify({'success': False, 'message': '当前没有运行中的穿环任务'}), 400

    ring_task.stop()
    return jsonify({'success': True, 'message': '穿环任务已停止'})


# ── 巡线任务端点 ──────────────────────────────────────────────

@app.route('/api/tello/line/start', methods=['POST'])
def line_start():
    """
    启动巡线任务。
    前置条件：无人机已连接且已起飞，并已调用 streamon（任务内部会确保）。
    任务运行期间，通过 WebSocket 事件 'line_status' 向前端推送实时状态。
    请求体（JSON，可选）：
        flip_vertical : bool  是否垂直翻转图像，默认 true（适用反射镜安装）
    """
    global tello, is_connected, line_task

    if not is_connected or tello is None:
        return jsonify({'success': False, 'message': '无人机未连接'}), 400

    if line_task is not None and line_task.is_running:
        return jsonify({'success': False, 'message': '巡线任务已在运行中'}), 400

    body         = request.get_json(silent=True) or {}
    flip_vertical = body.get('flip_vertical', True)

    # 确保视频流已开启
    try:
        tello.streamon()
    except Exception:
        pass  # 若已开启会抛出异常，忽略即可

    def on_line_status(data):
        socketio.emit('line_status', data)

    line_task = LineTask(tello, status_callback=on_line_status,
                         flip_vertical=flip_vertical)
    line_task.start()

    return jsonify({'success': True, 'message': '巡线任务已启动'})


@app.route('/api/tello/line/stop', methods=['POST'])
def line_stop():
    """安全停止巡线任务（无人机悬停，不自动降落）"""
    global line_task

    if line_task is None or not line_task.is_running:
        return jsonify({'success': False, 'message': '当前没有运行中的巡线任务'}), 400

    line_task.stop()
    return jsonify({'success': True, 'message': '巡线任务已停止'})


# ── 避障任务端点 ──────────────────────────────────────────────

@app.route('/api/tello/obstacle/start', methods=['POST'])
def obstacle_start():
    """
    启动避障任务。
    前置条件：无人机已连接且已起飞，已调用 streamon。
    任务运行期间，通过 WebSocket 事件 'obstacle_status' 向前端推送实时状态。
    """
    global tello, is_connected, obstacle_task

    if not is_connected or tello is None:
        return jsonify({'success': False, 'message': '无人机未连接'}), 400

    if obstacle_task is not None and obstacle_task.is_running:
        return jsonify({'success': False, 'message': '避障任务已在运行中'}), 400

    # 确保视频流已开启
    try:
        tello.streamon()
    except Exception:
        pass

    def on_obstacle_status(data):
        socketio.emit('obstacle_status', data)

    obstacle_task = ObstacleTask(tello, status_callback=on_obstacle_status)
    obstacle_task.start()

    return jsonify({'success': True, 'message': '避障任务已启动'})


@app.route('/api/tello/obstacle/stop', methods=['POST'])
def obstacle_stop():
    """安全停止避障任务（无人机悬停，不自动降落）"""
    global obstacle_task

    if obstacle_task is None or not obstacle_task.is_running:
        return jsonify({'success': False, 'message': '当前没有运行中的避障任务'}), 400

    obstacle_task.stop()
    return jsonify({'success': True, 'message': '避障任务已停止'})


def start_flask():
    """在单独线程中启动 SocketIO 服务器"""
    socketio.run(app, host='127.0.0.1', port=5000,
                 allow_unsafe_werkzeug=True, use_reloader=False)


if __name__ == '__main__':
    import sys

    # 开发模式：python backend_example.py dev
    # 仅启动 Flask API，前端单独运行 pnpm dev（localhost:5173）
    if len(sys.argv) > 1 and sys.argv[1] == 'dev':
        print('后端 API + WebSocket 已启动：http://127.0.0.1:5000')
        socketio.run(app, host='127.0.0.1', port=5000, debug=True,
                     allow_unsafe_werkzeug=True)

    # 生产模式（默认）：Flask + pywebview 嵌入前端
    else:
        try:
            import webview
        except ImportError:
            print('未安装 pywebview，请运行：pip install pywebview')
            print('或使用开发模式：python backend_example.py dev')
            sys.exit(1)

        # 后台启动 Flask
        flask_thread = threading.Thread(target=start_flask, daemon=True)
        flask_thread.start()
        time.sleep(1)  # 等待 Flask 就绪

        class Api:
            def minimize(self):
                window.minimize()

            def maximize(self):
                window.toggle_fullscreen()

            def close(self):
                window.destroy()

        window = webview.create_window(
            'Tello 无人机控制台',
            'http://localhost:5173',
            width=900,
            height=700,
            resizable=True,
            frameless=True
        )
        webview.start(api=Api())
