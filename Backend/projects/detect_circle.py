'''
* @file         detect_circle.py
* @brief        Tello 无人机穿越彩色圆环
* @details
    使用 HSV 颜色阈值 + 轮廓检测识别圆环，通过状态机控制穿越逻辑。
    连续 CONFIRM_FRAMES 帧保持对准后才执行穿越，保证精准和安全。

    状态机流程：
        SEARCHING  ── 偏航旋转搜索圆环
            ↓ 发现圆环
        CENTERING  ── 比例控制调整左右/上下，连续对准计数
            ↓ 连续 CONFIRM_FRAMES 帧偏差 < CENTER_TOL
        PASSING    ── 全速前进穿越，计时结束后切换
            ↓ 超时
        SEARCHING（下一个）或 DONE

    使用前准备：
        1. 用 ColorPicker.py 对实际圆环颜色进行标定
        2. 将标定结果填入 HSV_LOWER / HSV_UPPER
        3. 按需调整 CENTER_TOL、CONFIRM_FRAMES、PASS_TIME
'''

import cv2
import numpy as np
from djitellopy import tello
import time

# ===================== 颜色参数（用 ColorPicker.py 标定后修改） =====================
# 格式: np.array([H_min, S_min, V_min])  /  np.array([H_max, S_max, V_max])
HSV_LOWER = np.array([5,  120, 120])   # 橙色圆环参考值
HSV_UPPER = np.array([25, 255, 255])

# ===================== 控制参数 =====================
IMG_W          = 480    # 处理分辨率宽
IMG_H          = 360    # 处理分辨率高
MIN_AREA       = 800    # 有效轮廓最小面积（像素²），低于此视为噪声
CENTER_TOL     = 35     # 对准容差（像素），x/y 偏差均小于此值视为对准
CONFIRM_FRAMES = 20     # 连续对准帧数阈值，达到后才触发穿越（约 0.6 秒）
LOST_LIMIT     = 25     # CENTERING 中连续丢失帧数上限，超过后回到 SEARCHING
KP             = 0.15   # 对准比例控制系数
MAX_CTRL       = 30     # 对准控制量最大值（lr/ud 上限）
PASS_SPEED     = 35     # 穿越时前进速度（0~100）
PASS_TIME      = 2.0    # 穿越持续时间（秒），根据圆环间距调整
SEARCH_YAW     = 20     # 搜索时偏航速度（0~100）
TOTAL_RINGS    = 3      # 需要穿越的圆环总数
LOOP_DELAY     = 0.03   # 主循环延时（秒），约 33 fps，避免 confirm_count 在同一帧叠加

# ===================== 状态定义 =====================
SEARCHING = 'SEARCHING'
CENTERING = 'CENTERING'
PASSING   = 'PASSING'
DONE      = 'DONE'


# ===================== 圆环检测 =====================
def find_ring(img):
    '''
    在图像中检测彩色圆环。
    流程：HSV转换 → 颜色阈值 → 形态学降噪 → 轮廓筛选 → 取最大轮廓
    返回：(中心坐标(cx,cy), 轮廓面积, 掩膜图像)
          中心坐标为 None 时表示未检测到有效圆环。
    '''
    hsv  = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, HSV_LOWER, HSV_UPPER)

    # 开运算去除小噪点，闭运算填充轮廓内部孔洞
    k    = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, 0, mask

    biggest = max(contours, key=cv2.contourArea)
    area    = cv2.contourArea(biggest)
    if area < MIN_AREA:
        return None, 0, mask

    x, y, w, h = cv2.boundingRect(biggest)
    cx = x + w // 2
    cy = y + h // 2

    # 在图像上标注检测结果
    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
    cv2.circle(img, (cx, cy), 6, (0, 0, 255), cv2.FILLED)
    cv2.putText(img, f'Area:{int(area)}', (x, y - 8),
                cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 255, 0), 2)

    return (cx, cy), area, mask


# ===================== 比例控制量计算 =====================
def get_control(cx, cy):
    '''
    根据圆环中心与图像中心的偏差计算控制量。
    err_x > 0 → 圆环偏右 → lr 为正（向右移）
    err_y > 0 → 圆环偏下 → ud 为负（向下移），因此对 err_y 取反
    返回：(lr, ud, err_x, err_y)
    '''
    err_x = cx - IMG_W // 2
    err_y = cy - IMG_H // 2
    lr    = int(np.clip( err_x * KP, -MAX_CTRL, MAX_CTRL))
    ud    = int(np.clip(-err_y * KP, -MAX_CTRL, MAX_CTRL))
    return lr, ud, err_x, err_y


# ===================== 初始化无人机 =====================
me = tello.Tello()
me.connect()
print(f'电量: {me.get_battery()}%')
me.streamon()
time.sleep(1)
me.takeoff()
time.sleep(1.5)   # 等待无人机稳定悬停

# ===================== 主循环 =====================
state           = SEARCHING
confirm_count   = 0      # 连续对准帧计数
lost_count      = 0      # CENTERING 中连续丢失帧计数
rings_passed    = 0      # 已穿越圆环数
pass_start_time = None   # 穿越阶段开始时间戳

print(f'[开始] 目标穿越 {TOTAL_RINGS} 个圆环，当前状态: {state}')

while True:
    img              = me.get_frame_read().frame
    img              = cv2.resize(img, (IMG_W, IMG_H))
    center, area, mask = find_ring(img)

    # ─────────── SEARCHING ───────────
    if state == SEARCHING:
        confirm_count = 0
        lost_count    = 0
        if center is not None:
            print(f'[发现圆环] 面积={int(area)}，进入对准阶段')
            me.send_rc_control(0, 0, 0, 0)
            state = CENTERING
        else:
            me.send_rc_control(0, 0, 0, SEARCH_YAW)

    # ─────────── CENTERING ───────────
    elif state == CENTERING:
        if center is None:
            # 短暂丢失时悬停等待，避免立即放弃
            lost_count += 1
            me.send_rc_control(0, 0, 0, 0)
            if lost_count >= LOST_LIMIT:
                print('[丢失圆环] 回到搜索阶段')
                state = SEARCHING
        else:
            lost_count           = 0
            cx, cy               = center
            lr, ud, err_x, err_y = get_control(cx, cy)
            is_centered          = abs(err_x) < CENTER_TOL and abs(err_y) < CENTER_TOL

            if is_centered:
                confirm_count += 1
                me.send_rc_control(0, 0, 0, 0)   # 对准时悬停，不引入新偏差
                print(f'[对准确认 {confirm_count:2d}/{CONFIRM_FRAMES}]  '
                      f'偏差=({err_x:+4d}, {err_y:+4d})')
            else:
                # 偏差超限，重置计数，重新积累连续对准帧
                if confirm_count > 0:
                    print(f'[对准中断] 偏差=({err_x:+4d}, {err_y:+4d})，重置计数')
                confirm_count = 0
                me.send_rc_control(lr, 0, ud, 0)

            if confirm_count >= CONFIRM_FRAMES:
                print(f'[穿越开始] 第 {rings_passed + 1} 个圆环 ──────────────')
                pass_start_time = time.time()
                state           = PASSING

    # ─────────── PASSING ───────────
    elif state == PASSING:
        elapsed = time.time() - pass_start_time
        if elapsed < PASS_TIME:
            me.send_rc_control(0, PASS_SPEED, 0, 0)
        else:
            me.send_rc_control(0, 0, 0, 0)
            time.sleep(0.5)          # 穿越后短暂悬停，等待无人机稳定
            rings_passed   += 1
            confirm_count   = 0
            lost_count      = 0
            pass_start_time = None
            print(f'[穿越完成] 已穿越 {rings_passed}/{TOTAL_RINGS} 个')
            state = DONE if rings_passed >= TOTAL_RINGS else SEARCHING

    # ─────────── DONE ───────────
    elif state == DONE:
        print('[全部完成] 准备降落')
        me.land()
        break

    # ─────────── 画面标注 ───────────
    # 图像中心十字准线
    cx_img, cy_img = IMG_W // 2, IMG_H // 2
    cv2.line(img, (cx_img - 20, cy_img), (cx_img + 20, cy_img), (255, 0, 0), 1)
    cv2.line(img, (cx_img, cy_img - 20), (cx_img, cy_img + 20), (255, 0, 0), 1)

    cv2.putText(img,
                f'State:{state}  Ring:{rings_passed}/{TOTAL_RINGS}  '
                f'Confirm:{confirm_count}/{CONFIRM_FRAMES}',
                (8, 25), cv2.FONT_HERSHEY_PLAIN, 1.2, (0, 255, 255), 2)

    cv2.imshow('Tello - Ring Detection', img)
    cv2.imshow('Mask', mask)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        me.land()
        break

    time.sleep(LOOP_DELAY)   # 限制帧率，防止 confirm_count 在同一帧快速叠加

cv2.destroyAllWindows()
