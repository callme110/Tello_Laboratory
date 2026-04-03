import { useState, useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { Minus, Square, X, Wifi, Battery, Plane, ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Circle, GitBranch, Shield, MoveDown } from 'lucide-react';

// ── 穿环任务状态类型 ──────────────────────────────────────────
interface RingStatus {
  state: 'IDLE' | 'SEARCHING' | 'CENTERING' | 'PASSING' | 'DONE';
  rings_passed:   number;
  total_rings:    number;
  confirm_count:  number;
  confirm_target: number;
  err_x: number;
  err_y: number;
}

const RING_STATE_LABELS: Record<string, { text: string; color: string }> = {
  IDLE:      { text: '空闲',     color: 'text-slate-400'  },
  SEARCHING: { text: '搜索圆环', color: 'text-yellow-400' },
  CENTERING: { text: '对准中',   color: 'text-blue-400'   },
  PASSING:   { text: '穿越中',   color: 'text-emerald-400'},
  DONE:      { text: '已完成',   color: 'text-green-400'  },
};

// ── 巡线任务状态类型 ──────────────────────────────────────────
interface LineStatus {
  state:      'IDLE' | 'FOLLOWING' | 'LOST';
  cx:         number;   // 检测到的线中心 x（像素）
  err:        number;   // 偏差（正=偏右）
  yaw:        number;   // 偏航控制量
  lr:         number;   // 左右平移控制量
  sensors:    [number, number, number];  // [L, C, R]
  lost_count: number;
  img_w:      number;   // 图像宽度（用于计算偏差百分比）
}

const LINE_STATE_LABELS: Record<string, { text: string; color: string }> = {
  IDLE:      { text: '空闲',   color: 'text-slate-400'  },
  FOLLOWING: { text: '巡线中', color: 'text-cyan-400'   },
  LOST:      { text: '线丢失', color: 'text-red-400'    },
};

// ── 避障任务状态类型 ──────────────────────────────────────────
interface ObstacleStatus {
  state:          'IDLE' | 'FORWARD' | 'AVOIDING';
  obstacle_ratio: number;   // 障碍物像素占比（0~1）
  obstacle_cx:    number;   // 障碍物质心 x（像素）
  avoid_dir:      number;   // 横移方向：正=右，负=左，0=未避障
  img_w:          number;
}

const OBSTACLE_STATE_LABELS: Record<string, { text: string; color: string }> = {
  IDLE:     { text: '空闲',   color: 'text-slate-400'  },
  FORWARD:  { text: '前进中', color: 'text-amber-400'  },
  AVOIDING: { text: '绕障中', color: 'text-orange-400' },
};

export default function App() {
  const [isConnected, setIsConnected] = useState(false);
  const [battery, setBattery] = useState(0);
  const [isConnecting, setIsConnecting] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [activeKeys, setActiveKeys] = useState<Set<string>>(new Set());
  const [ringStatus, setRingStatus]   = useState<RingStatus | null>(null);
  const [ringRunning, setRingRunning] = useState(false);
  const [lineStatus, setLineStatus]         = useState<LineStatus | null>(null);
  const [lineRunning, setLineRunning]       = useState(false);
  const [obstacleStatus, setObstacleStatus] = useState<ObstacleStatus | null>(null);
  const [obstacleRunning, setObstacleRunning] = useState(false);

  const BACKEND = 'http://127.0.0.1:5000';
  const socketRef = useRef<Socket | null>(null);

  // ── 连接无人机 ────────────────────────────────────────────
  const handleConnect = async () => {
    setIsConnecting(true);
    setConnectError(null);

    try {
      const res = await fetch(`${BACKEND}/api/tello/connect`, {
        method: 'GET',
        signal: AbortSignal.timeout(10000),
      });
      const data = await res.json();

      if (data.success) {
        setIsConnected(true);
        setBattery(data.battery ?? 0);
      } else {
        setConnectError(data.message || '连接失败，请检查无人机是否开机');
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'TimeoutError') {
        setConnectError('连接超时，请确认无人机已开机并连接到 Tello Wi-Fi');
      } else {
        setConnectError('无法连接后端服务，请先运行 python backend_example.py dev');
      }
    } finally {
      setIsConnecting(false);
    }
  };

  // ── Socket.IO 连接（无人机连上后建立）───────────────────
  useEffect(() => {
    if (!isConnected) return;

    const socket = io(BACKEND, { transports: ['websocket'] });
    socketRef.current = socket;

    // 穿环实时状态推送
    socket.on('ring_status', (data: RingStatus) => {
      setRingStatus(data);
      setRingRunning(data.state !== 'IDLE' && data.state !== 'DONE');
    });

    // 巡线实时状态推送
    socket.on('line_status', (data: LineStatus) => {
      setLineStatus(data);
      setLineRunning(data.state === 'FOLLOWING');
    });

    // 避障实时状态推送
    socket.on('obstacle_status', (data: ObstacleStatus) => {
      setObstacleStatus(data);
      setObstacleRunning(data.state !== 'IDLE');
    });

    return () => {
      socket.disconnect();
      socketRef.current = null;
    };
  }, [isConnected]);

  // ── 穿环任务控制 ─────────────────────────────────────────
  const handleRingStart = async () => {
    try {
      const res  = await fetch(`${BACKEND}/api/tello/ring/start`, { method: 'POST' });
      const data = await res.json();
      if (data.success) setRingRunning(true);
      else alert(data.message);
    } catch {
      alert('穿环启动失败：无法连接后端');
    }
  };

  const handleRingStop = async () => {
    try {
      await fetch(`${BACKEND}/api/tello/ring/stop`, { method: 'POST' });
      setRingRunning(false);
    } catch {
      alert('停止请求失败');
    }
  };

  // ── 巡线任务控制 ─────────────────────────────────────────
  const handleLineStart = async () => {
    try {
      const res  = await fetch(`${BACKEND}/api/tello/line/start`, { method: 'POST' });
      const data = await res.json();
      if (data.success) setLineRunning(true);
      else alert(data.message);
    } catch {
      alert('巡线启动失败：无法连接后端');
    }
  };

  const handleLineStop = async () => {
    try {
      await fetch(`${BACKEND}/api/tello/line/stop`, { method: 'POST' });
      setLineRunning(false);
    } catch {
      alert('停止请求失败');
    }
  };

  // ── 降落 ─────────────────────────────────────────────────
  const handleLand = async () => {
    try {
      const res  = await fetch(`${BACKEND}/api/tello/land`, { method: 'POST' });
      const data = await res.json();
      if (!data.success) alert(data.message);
    } catch {
      alert('降落指令发送失败：无法连接后端');
    }
  };

  // ── 避障任务控制 ─────────────────────────────────────────
  const handleObstacleStart = async () => {
    try {
      const res  = await fetch(`${BACKEND}/api/tello/obstacle/start`, { method: 'POST' });
      const data = await res.json();
      if (data.success) setObstacleRunning(true);
      else alert(data.message);
    } catch {
      alert('避障启动失败：无法连接后端');
    }
  };

  const handleObstacleStop = async () => {
    try {
      await fetch(`${BACKEND}/api/tello/obstacle/stop`, { method: 'POST' });
      setObstacleRunning(false);
    } catch {
      alert('停止请求失败');
    }
  };

  // ── 键盘事件 → WebSocket ─────────────────────────────────
  // 覆盖方向键 / W S A D / E Q，防止页面滚动
  const CONTROLLED_KEYS = new Set([
    'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
    'w', 's', 'a', 'd', 'e', 'q',
  ]);

  useEffect(() => {
    if (!isConnected) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (!CONTROLLED_KEYS.has(e.key)) return;
      e.preventDefault();           // 阻止方向键滚动页面
      if (e.repeat) return;         // 忽略系统自动重复
      setActiveKeys(prev => new Set([...prev, e.key]));
      socketRef.current?.emit('key_down', { key: e.key });
    };

    const onKeyUp = (e: KeyboardEvent) => {
      if (!CONTROLLED_KEYS.has(e.key)) return;
      setActiveKeys(prev => {
        const next = new Set(prev);
        next.delete(e.key);
        return next;
      });
      socketRef.current?.emit('key_up', { key: e.key });
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
    };
  }, [isConnected]);

  // ── 方向按钮（屏幕点击 / 触屏）──────────────────────────
  // direction → 对应键名，与键盘 mapping 一致
  const DIR_KEY: Record<string, string> = {
    '上': 'ArrowUp',
    '下': 'ArrowDown',
    '左': 'ArrowLeft',
    '右': 'ArrowRight',
  };

  const handleDirDown = (direction: string) => {
    const key = DIR_KEY[direction];
    if (!key) return;
    setActiveKeys(prev => new Set([...prev, key]));
    socketRef.current?.emit('key_down', { key });
  };

  const handleDirUp = (direction: string) => {
    const key = DIR_KEY[direction];
    if (!key) return;
    setActiveKeys(prev => {
      const next = new Set(prev);
      next.delete(key);
      return next;
    });
    socketRef.current?.emit('key_up', { key });
  };

  // ── 窗口控制 ─────────────────────────────────────────────
  const handleMinimize = () => console.log('最小化窗口');
  const handleMaximize = () => console.log('最大化窗口');
  const handleClose    = () => console.log('关闭应用');

  const handleFunction = (funcName: string) => {
    if (funcName === '穿环') {
      handleRingStart();
      return;
    }
    if (funcName === '巡线') {
      handleLineStart();
      return;
    }
    if (funcName === '避障') {
      handleObstacleStart();
      return;
    }
    if (funcName === '降落') {
      handleLand();
      return;
    }
    console.log(`执行功能: ${funcName}`);
  };

  return (
    <div className="size-full flex items-center justify-center bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900">
      {/* 背景装饰 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500 rounded-full mix-blend-multiply filter blur-3xl opacity-10 animate-pulse"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-500 rounded-full mix-blend-multiply filter blur-3xl opacity-10 animate-pulse" style={{ animationDelay: '1s' }}></div>
      </div>

      <div className="w-[900px] bg-gradient-to-b from-slate-800 to-slate-900 rounded-2xl shadow-2xl overflow-hidden border border-slate-700 relative z-10">
        {/* 自定义标题栏 */}
        <div className="bg-gradient-to-r from-blue-600 via-blue-700 to-indigo-700 px-6 py-4 flex items-center justify-between border-b border-blue-500/30">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white/10 rounded-lg flex items-center justify-center backdrop-blur-sm">
              <Plane className="w-5 h-5 text-white" />
            </div>
            <h1 className="text-white tracking-wide">Tello</h1>
          </div>

          {/* 窗口控制按钮 */}
          <div className="flex items-center gap-1">
            <button
              onClick={handleMinimize}
              className="w-9 h-9 flex items-center justify-center rounded-lg hover:bg-white/10 transition-all backdrop-blur-sm"
              title="最小化"
            >
              <Minus className="w-4 h-4 text-white" />
            </button>
            <button
              onClick={handleMaximize}
              className="w-9 h-9 flex items-center justify-center rounded-lg hover:bg-white/10 transition-all backdrop-blur-sm"
              title="最大化"
            >
              <Square className="w-4 h-4 text-white" />
            </button>
            <button
              onClick={handleClose}
              className="w-9 h-9 flex items-center justify-center rounded-lg hover:bg-red-500 transition-all backdrop-blur-sm"
              title="关闭"
            >
              <X className="w-4 h-4 text-white" />
            </button>
          </div>
        </div>

        {/* 主内容区域 */}
        <div className="p-8">
          {/* 电量显示区域 - 连接成功后显示 */}
          {isConnected && (
            <div className="mb-6 p-6 bg-gradient-to-br from-emerald-500/20 to-green-500/20 rounded-xl border border-emerald-400/30 backdrop-blur-sm relative overflow-hidden">
              <div className="absolute top-0 right-0 w-32 h-32 bg-green-400 rounded-full filter blur-3xl opacity-20"></div>
              <div className="relative">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 bg-emerald-500/20 rounded-lg flex items-center justify-center">
                    <Battery className="w-5 h-5 text-emerald-400" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between">
                      <span className="text-emerald-300">电池电量</span>
                      <span className="text-emerald-100">{battery}%</span>
                    </div>
                  </div>
                </div>
                <div className="w-full bg-slate-700/50 rounded-full h-3 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-emerald-400 to-green-500 h-3 rounded-full transition-all duration-500 shadow-lg shadow-emerald-500/50"
                    style={{ width: `${battery}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* 连接状态卡片 */}
          <div className="mb-6 p-6 bg-slate-800/50 rounded-xl border border-slate-700 backdrop-blur-sm">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                  isConnected ? 'bg-emerald-500/20' : 'bg-slate-700/50'
                } transition-all duration-300`}>
                  <Wifi className={`w-6 h-6 ${isConnected ? 'text-emerald-400' : 'text-slate-400'}`} />
                </div>
                <div>
                  <div className="text-slate-400 text-sm">连接状态</div>
                  <div className="flex items-center gap-2 mt-1">
                    <div className={`w-2 h-2 rounded-full ${
                      isConnected ? 'bg-emerald-400 animate-pulse shadow-lg shadow-emerald-500/50' : 'bg-slate-500'
                    }`} />
                    <span className={isConnected ? 'text-emerald-300' : 'text-slate-400'}>
                      {isConnected ? '已连接到无人机' : '未连接'}
                    </span>
                  </div>
                </div>
              </div>

              {isConnected && (
                <div className="text-right">
                  <div className="text-slate-400 text-sm">信号强度</div>
                  <div className="flex gap-1 mt-1">
                    {[1, 2, 3, 4].map((bar) => (
                      <div
                        key={bar}
                        className="w-1 bg-emerald-400 rounded-full"
                        style={{ height: `${bar * 4 + 4}px` }}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* 功能控制区域 - 连接成功后显示 */}
          {isConnected && (
            <div className="mb-6 grid grid-cols-2 gap-6">
              {/* 左侧：功能按钮 */}
              <div className="space-y-4">
                <div className="text-slate-300 mb-3 flex items-center gap-2">
                  <div className="w-1 h-4 bg-blue-500 rounded"></div>
                  <span>功能控制</span>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={() => handleFunction('穿环')}
                    disabled={ringRunning}
                    className={`p-4 border rounded-xl transition-all duration-300 group
                      ${ringRunning
                        ? 'bg-purple-500/40 border-purple-400/60 cursor-not-allowed'
                        : 'bg-gradient-to-br from-purple-500/20 to-purple-600/20 hover:from-purple-500/30 hover:to-purple-600/30 border-purple-500/30'
                      }`}
                  >
                    <Circle className={`w-6 h-6 text-purple-400 mx-auto mb-2 transition-transform
                      ${ringRunning ? 'animate-spin' : 'group-hover:scale-110'}`} />
                    <div className="text-purple-300 text-sm">
                      {ringRunning ? '穿环中…' : '穿环'}
                    </div>
                  </button>
                  <button
                    onClick={() => handleFunction('巡线')}
                    disabled={lineRunning}
                    className={`p-4 border rounded-xl transition-all duration-300 group
                      ${lineRunning
                        ? 'bg-cyan-500/40 border-cyan-400/60 cursor-not-allowed'
                        : 'bg-gradient-to-br from-cyan-500/20 to-cyan-600/20 hover:from-cyan-500/30 hover:to-cyan-600/30 border-cyan-500/30'
                      }`}
                  >
                    <GitBranch className={`w-6 h-6 text-cyan-400 mx-auto mb-2 transition-transform
                      ${lineRunning ? 'animate-pulse' : 'group-hover:scale-110'}`} />
                    <div className="text-cyan-300 text-sm">
                      {lineRunning ? '巡线中…' : '巡线'}
                    </div>
                  </button>
                  <button
                    onClick={() => handleFunction('避障')}
                    disabled={obstacleRunning}
                    className={`p-4 border rounded-xl transition-all duration-300 group
                      ${obstacleRunning
                        ? 'bg-amber-500/40 border-amber-400/60 cursor-not-allowed'
                        : 'bg-gradient-to-br from-amber-500/20 to-amber-600/20 hover:from-amber-500/30 hover:to-amber-600/30 border-amber-500/30'
                      }`}
                  >
                    <Shield className={`w-6 h-6 text-amber-400 mx-auto mb-2 transition-transform
                      ${obstacleRunning ? 'animate-pulse' : 'group-hover:scale-110'}`} />
                    <div className="text-amber-300 text-sm">
                      {obstacleRunning ? '避障中…' : '避障'}
                    </div>
                  </button>
                  <button
                    onClick={() => handleFunction('降落')}
                    className="p-4 bg-gradient-to-br from-red-500/20 to-red-600/20 hover:from-red-500/30 hover:to-red-600/30 border border-red-500/30 rounded-xl transition-all duration-300 group"
                  >
                    <MoveDown className="w-6 h-6 text-red-400 mx-auto mb-2 group-hover:scale-110 transition-transform" />
                    <div className="text-red-300 text-sm">降落</div>
                  </button>
                </div>

                {/* 穿环任务进度面板 */}
                {ringStatus && ringStatus.state !== 'IDLE' && (
                  <div className="mt-4 p-4 bg-purple-500/10 border border-purple-500/30 rounded-xl space-y-3">

                    {/* 标题行：状态 + 圆环计数 */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${
                          ringRunning ? 'bg-purple-400 animate-pulse' : 'bg-green-400'
                        }`} />
                        <span className={`text-sm font-medium ${
                          RING_STATE_LABELS[ringStatus.state]?.color ?? 'text-slate-400'
                        }`}>
                          {RING_STATE_LABELS[ringStatus.state]?.text ?? ringStatus.state}
                        </span>
                      </div>
                      <div className="flex gap-1.5">
                        {Array.from({ length: ringStatus.total_rings }).map((_, i) => (
                          <div
                            key={i}
                            className={`w-6 h-6 rounded-full border-2 flex items-center justify-center text-xs font-bold transition-all
                              ${i < ringStatus.rings_passed
                                ? 'border-purple-400 bg-purple-500/40 text-purple-200'
                                : i === ringStatus.rings_passed && ringRunning
                                  ? 'border-yellow-400 bg-yellow-500/20 text-yellow-300 animate-pulse'
                                  : 'border-slate-600 text-slate-500'
                              }`}
                          >
                            {i + 1}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* 对准进度条（仅 CENTERING 阶段）*/}
                    {ringStatus.state === 'CENTERING' && (
                      <div className="space-y-1.5">
                        <div className="flex justify-between text-xs text-slate-500">
                          <span>对准确认</span>
                          <span>{ringStatus.confirm_count} / {ringStatus.confirm_target} 帧</span>
                        </div>
                        <div className="w-full bg-slate-700 rounded-full h-2 overflow-hidden">
                          <div
                            className="bg-gradient-to-r from-purple-500 to-indigo-400 h-2 rounded-full transition-all duration-100"
                            style={{ width: `${Math.min(100, (ringStatus.confirm_count / ringStatus.confirm_target) * 100)}%` }}
                          />
                        </div>
                        <div className="flex justify-between text-xs">
                          <span className="text-slate-500">偏差 X: <span className={Math.abs(ringStatus.err_x) < 35 ? 'text-emerald-400' : 'text-red-400'}>
                            {ringStatus.err_x > 0 ? '+' : ''}{ringStatus.err_x} px
                          </span></span>
                          <span className="text-slate-500">偏差 Y: <span className={Math.abs(ringStatus.err_y) < 35 ? 'text-emerald-400' : 'text-red-400'}>
                            {ringStatus.err_y > 0 ? '+' : ''}{ringStatus.err_y} px
                          </span></span>
                        </div>
                      </div>
                    )}

                    {/* 停止按钮 */}
                    {ringRunning && (
                      <button
                        onClick={handleRingStop}
                        className="w-full py-1.5 bg-red-500/20 hover:bg-red-500/30 border border-red-500/40 rounded-lg text-red-300 text-xs transition-all"
                      >
                        停止任务
                      </button>
                    )}
                  </div>
                )}

                {/* 巡线任务状态面板 */}
                {lineStatus && lineStatus.state !== 'IDLE' && (
                  <div className="mt-4 p-4 bg-cyan-500/10 border border-cyan-500/30 rounded-xl space-y-3">

                    {/* 标题行：状态文字 + 指示灯 */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${
                          lineStatus.state === 'FOLLOWING'
                            ? 'bg-cyan-400 animate-pulse'
                            : 'bg-red-400'
                        }`} />
                        <span className={`text-sm font-medium ${
                          LINE_STATE_LABELS[lineStatus.state]?.color ?? 'text-slate-400'
                        }`}>
                          {LINE_STATE_LABELS[lineStatus.state]?.text ?? lineStatus.state}
                        </span>
                      </div>
                      {lineStatus.state === 'LOST' && (
                        <span className="text-xs text-red-400">
                          丢线 {lineStatus.lost_count} 帧
                        </span>
                      )}
                    </div>

                    {/* 3 虚拟传感器可视化 */}
                    <div className="space-y-1">
                      <div className="text-xs text-slate-500">虚拟传感器  (左 / 中 / 右)</div>
                      <div className="flex gap-2">
                        {(['左', '中', '右'] as const).map((label, i) => (
                          <div
                            key={i}
                            className={`flex-1 h-7 rounded flex items-center justify-center text-xs font-bold border transition-all
                              ${lineStatus.sensors[i]
                                ? 'bg-cyan-500/40 border-cyan-400 text-cyan-200'
                                : 'bg-slate-700/40 border-slate-600 text-slate-500'
                              }`}
                          >
                            {label}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* 横向偏差指示条（FOLLOWING 状态才有意义）*/}
                    {lineStatus.state === 'FOLLOWING' && (
                      <div className="space-y-1">
                        <div className="flex justify-between text-xs text-slate-500">
                          <span>横向偏差</span>
                          <span className={Math.abs(lineStatus.err) < lineStatus.img_w * 0.1
                            ? 'text-emerald-400' : 'text-yellow-400'}>
                            {lineStatus.err > 0 ? '+' : ''}{lineStatus.err} px
                          </span>
                        </div>
                        {/* 偏差条：以中心为零点，左右各代表偏左/偏右 */}
                        <div className="relative w-full h-3 bg-slate-700 rounded-full overflow-hidden">
                          {/* 中心参考线 */}
                          <div className="absolute left-1/2 top-0 h-full w-0.5 bg-slate-500 -translate-x-1/2" />
                          {/* 偏差块 */}
                          <div
                            className={`absolute top-0 h-full rounded-full transition-all duration-100 ${
                              Math.abs(lineStatus.err) < lineStatus.img_w * 0.1
                                ? 'bg-emerald-400'
                                : 'bg-yellow-400'
                            }`}
                            style={{
                              width: `${Math.min(50, Math.abs(lineStatus.err) / lineStatus.img_w * 100)}%`,
                              left: lineStatus.err >= 0
                                ? '50%'
                                : `${50 - Math.min(50, Math.abs(lineStatus.err) / lineStatus.img_w * 100)}%`,
                            }}
                          />
                        </div>
                        {/* 偏航 / 平移控制量 */}
                        <div className="flex justify-between text-xs text-slate-500 pt-0.5">
                          <span>偏航: <span className="text-cyan-300">{lineStatus.yaw > 0 ? '+' : ''}{lineStatus.yaw}</span></span>
                          <span>平移: <span className="text-cyan-300">{lineStatus.lr > 0 ? '+' : ''}{lineStatus.lr}</span></span>
                        </div>
                      </div>
                    )}

                    {/* 停止按钮 */}
                    {lineRunning && (
                      <button
                        onClick={handleLineStop}
                        className="w-full py-1.5 bg-red-500/20 hover:bg-red-500/30 border border-red-500/40 rounded-lg text-red-300 text-xs transition-all"
                      >
                        停止巡线
                      </button>
                    )}
                  </div>
                )}

                {/* 避障任务状态面板 */}
                {obstacleStatus && obstacleStatus.state !== 'IDLE' && (
                  <div className="mt-4 p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl space-y-3">

                    {/* 标题行：状态文字 + 覆盖率 */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full animate-pulse ${
                          obstacleStatus.state === 'AVOIDING' ? 'bg-orange-400' : 'bg-amber-400'
                        }`} />
                        <span className={`text-sm font-medium ${
                          OBSTACLE_STATE_LABELS[obstacleStatus.state]?.color ?? 'text-slate-400'
                        }`}>
                          {OBSTACLE_STATE_LABELS[obstacleStatus.state]?.text ?? obstacleStatus.state}
                        </span>
                      </div>
                      <span className={`text-xs ${
                        obstacleStatus.obstacle_ratio >= 0.08 ? 'text-orange-400' : 'text-slate-500'
                      }`}>
                        覆盖率 {(obstacleStatus.obstacle_ratio * 100).toFixed(1)}%
                      </span>
                    </div>

                    {/* 障碍物位置指示（AVOIDING 时显示） */}
                    {obstacleStatus.state === 'AVOIDING' && (
                      <div className="space-y-1">
                        <div className="text-xs text-slate-500">
                          障碍物位置 &nbsp;→&nbsp;
                          <span className="text-orange-300">
                            {obstacleStatus.avoid_dir > 0 ? '向右绕行' : '向左绕行'}
                          </span>
                        </div>
                        <div className="relative w-full h-4 bg-slate-700 rounded-full overflow-hidden">
                          <div className="absolute left-1/2 top-0 h-full w-0.5 bg-slate-500 -translate-x-1/2" />
                          {obstacleStatus.obstacle_cx > 0 && (
                            <div
                              className="absolute top-1 h-2 w-2 bg-orange-400 rounded-full -translate-x-1/2 transition-all duration-100"
                              style={{ left: `${(obstacleStatus.obstacle_cx / obstacleStatus.img_w) * 100}%` }}
                            />
                          )}
                        </div>
                        <div className="flex justify-between text-xs text-slate-600">
                          <span>左</span><span>右</span>
                        </div>
                      </div>
                    )}

                    {/* 停止按钮 */}
                    {obstacleRunning && (
                      <button
                        onClick={handleObstacleStop}
                        className="w-full py-1.5 bg-red-500/20 hover:bg-red-500/30 border border-red-500/40 rounded-lg text-red-300 text-xs transition-all"
                      >
                        停止避障
                      </button>
                    )}
                  </div>
                )}
              </div>

              <div>
                <div className="text-slate-300 mb-3 flex items-center gap-2">
                  <div className="w-1 h-4 bg-blue-500 rounded"></div>
                  <span>姿态微调</span>
                </div>
                <div className="flex items-center justify-center">
                  <div className="relative w-48 h-48">
                    {/* 上 / ArrowUp */}
                    <button
                      onPointerDown={() => handleDirDown('上')}
                      onPointerUp={() => handleDirUp('上')}
                      onPointerLeave={() => handleDirUp('上')}
                      className={`absolute top-0 left-1/2 -translate-x-1/2 w-14 h-14 border border-blue-500/40 rounded-lg flex items-center justify-center transition-all duration-150 shadow-lg select-none
                        ${activeKeys.has('ArrowUp')
                          ? 'bg-blue-500/70 shadow-blue-400/60 scale-95'
                          : 'bg-gradient-to-b from-blue-500/30 to-blue-600/30 hover:from-blue-500/50 hover:to-blue-600/50 hover:scale-110 hover:shadow-blue-500/50'
                        }`}
                    >
                      <ArrowUp className="w-6 h-6 text-blue-300" />
                    </button>

                    {/* 下 / ArrowDown */}
                    <button
                      onPointerDown={() => handleDirDown('下')}
                      onPointerUp={() => handleDirUp('下')}
                      onPointerLeave={() => handleDirUp('下')}
                      className={`absolute bottom-0 left-1/2 -translate-x-1/2 w-14 h-14 border border-blue-500/40 rounded-lg flex items-center justify-center transition-all duration-150 shadow-lg select-none
                        ${activeKeys.has('ArrowDown')
                          ? 'bg-blue-500/70 shadow-blue-400/60 scale-95'
                          : 'bg-gradient-to-t from-blue-500/30 to-blue-600/30 hover:from-blue-500/50 hover:to-blue-600/50 hover:scale-110 hover:shadow-blue-500/50'
                        }`}
                    >
                      <ArrowDown className="w-6 h-6 text-blue-300" />
                    </button>

                    {/* 左 / ArrowLeft */}
                    <button
                      onPointerDown={() => handleDirDown('左')}
                      onPointerUp={() => handleDirUp('左')}
                      onPointerLeave={() => handleDirUp('左')}
                      className={`absolute left-0 top-1/2 -translate-y-1/2 w-14 h-14 border border-blue-500/40 rounded-lg flex items-center justify-center transition-all duration-150 shadow-lg select-none
                        ${activeKeys.has('ArrowLeft')
                          ? 'bg-blue-500/70 shadow-blue-400/60 scale-95'
                          : 'bg-gradient-to-r from-blue-500/30 to-blue-600/30 hover:from-blue-500/50 hover:to-blue-600/50 hover:scale-110 hover:shadow-blue-500/50'
                        }`}
                    >
                      <ArrowLeft className="w-6 h-6 text-blue-300" />
                    </button>

                    {/* 右 / ArrowRight */}
                    <button
                      onPointerDown={() => handleDirDown('右')}
                      onPointerUp={() => handleDirUp('右')}
                      onPointerLeave={() => handleDirUp('右')}
                      className={`absolute right-0 top-1/2 -translate-y-1/2 w-14 h-14 border border-blue-500/40 rounded-lg flex items-center justify-center transition-all duration-150 shadow-lg select-none
                        ${activeKeys.has('ArrowRight')
                          ? 'bg-blue-500/70 shadow-blue-400/60 scale-95'
                          : 'bg-gradient-to-l from-blue-500/30 to-blue-600/30 hover:from-blue-500/50 hover:to-blue-600/50 hover:scale-110 hover:shadow-blue-500/50'
                        }`}
                    >
                      <ArrowRight className="w-6 h-6 text-blue-300" />
                    </button>

                    {/* 中心装饰 */}
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-16 h-16 bg-slate-700/50 rounded-full border border-slate-600 flex items-center justify-center">
                      <Plane className="w-6 h-6 text-slate-400" />
                    </div>
                  </div>
                </div>

                {/* 键盘快捷键说明 */}
                <div className="mt-4 grid grid-cols-2 gap-1 text-xs text-slate-500">
                  <span><kbd className="px-1 py-0.5 bg-slate-700 rounded text-slate-400">⬆⬇⬅➡</kbd> 前后左右</span>
                  <span><kbd className="px-1 py-0.5 bg-slate-700 rounded text-slate-400">W / S</kbd> 升 / 降</span>
                  <span><kbd className="px-1 py-0.5 bg-slate-700 rounded text-slate-400">A / D</kbd> 左转 / 右转</span>
                  <span><kbd className="px-1 py-0.5 bg-slate-700 rounded text-slate-400">E</kbd> 起飞  <kbd className="px-1 py-0.5 bg-slate-700 rounded text-slate-400">Q</kbd> 降落</span>
                </div>
              </div>
            </div>
          )}

          {/* 连接按钮 */}
          <button
            onClick={handleConnect}
            disabled={isConnected || isConnecting}
            className="w-full py-5 px-6 bg-gradient-to-r from-blue-500 to-indigo-600 text-white rounded-xl hover:from-blue-600 hover:to-indigo-700 disabled:from-slate-700 disabled:to-slate-700 disabled:cursor-not-allowed transition-all duration-300 shadow-lg hover:shadow-xl hover:shadow-blue-500/50 disabled:shadow-none relative overflow-hidden group"
          >
            <span className="relative z-10 flex items-center justify-center gap-2">
              {isConnecting && (
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              {isConnecting ? '正在连接中...' : isConnected ? '已连接' : '检测连接'}
            </span>
            {!isConnected && !isConnecting && (
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent translate-x-[-200%] group-hover:translate-x-[200%] transition-transform duration-1000" />
            )}
          </button>

          {/* 连接错误提示 */}
          {connectError && (
            <div className="mt-4 p-4 bg-red-500/10 border border-red-500/30 rounded-xl flex items-start gap-3">
              <div className="w-5 h-5 mt-0.5 shrink-0 rounded-full bg-red-500/20 flex items-center justify-center">
                <span className="text-red-400 text-xs font-bold">!</span>
              </div>
              <span className="text-red-300 text-sm leading-relaxed">{connectError}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}