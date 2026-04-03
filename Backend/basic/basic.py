from djitellopy import tello
from time import sleep

# tello 无人机的基本操作
tello = tello.Tello()
tello.connect()
tello.streamon()
sleep(2)

count = 3
# 设置飞机的飞行速度 15cm/s
tello.set_speed(15)
# send_rc_control 每次移动的时间为 0.5
while count > 0:
    print("无人机当前电量为：" + tello.get_battery())

    # 准备穿越第一个环
    tello.move_forward(150)
    sleep(0.5)
    count = count - 1
    print("无人机当前电量为：" + tello.get_battery())

    # 向左移动为穿越第二个环做准备
    tello.move_left(130)
    sleep(0.2)
    tello.move_left(70)
    sleep(0.2)
    tello.move_left(100)
    sleep(0.2)
    print("无人机当前电量为：" + tello.get_battery())

    # 准备穿越第二个环
    tello.move_forward(150)
    sleep(0.2)
    count = count - 1
    print("无人机当前的电量为：" + tello.get_battery())

    # 向右移动为穿越第三个环做准备
    tello.move_right(130)
    sleep(0.2)
    tello.move_right(70)
    sleep(0.2)
    tello.move_right(100)
    sleep(0.2)
    print("无人机当前电量为：" + tello.get_battery())

    # 准备穿越第三个环
    tello.move_forward(150)
    sleep(0.2)
    count = count - 1
    print("无人机当前电量为：" + tello.get_battery())

# 穿越三个环之后 降落
tello.land()
