from djitellopy import tello
import KeyPressModule as kp
from time import sleep

kp.init()

me = tello.Tello()
me.connect()
print("无人机当前电量为：", me.get_battery()) # 查看无人机电量

def getKeyboardInput():
    lr, fb, ud, yv = 0, 0, 0, 0 #lr:左右；fb：前后；ud：上下；yv：旋转角度
    speed = 50
    if kp.getKey('LEFT'):   lr = -speed
    elif kp.getKey('RIGHT'):    lr = speed

    if kp.getKey('UP'):   fb = speed
    elif kp.getKey('DOWN'):    fb = -speed

    if kp.getKey('w'):   ud = -speed
    elif kp.getKey('s'):    ud = speed

    if kp.getKey('a'):   yv = speed
    elif kp.getKey('d'):    yv = -speed

    if kp.getKey('q'):   me.land()
    if kp.getKey('e'):   me.takeoff()

    return [lr, fb, ud, yv]

while True:
    # 按按键的时候，鼠标应该点在pygame创建的窗口里。
    vals = getKeyboardInput()
    me.send_rc_control(vals[0], vals[1], vals[2], vals[3] )
    sleep(0.05) # 设置一个延时，避免按键过快造成无人机来不及反应

