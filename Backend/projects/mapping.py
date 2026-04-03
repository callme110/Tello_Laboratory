# 这个程序用来画出飞行轨迹，拷贝了KeyboardControl文件的代码做修改。

from djitellopy import tello
import KeyPressModule as kp
import numpy as np
import cv2
import math
import time

###### PARAMETERS（参数） ######
# 向前的速度117cm/10sec,视频上说这是讲者通过测试摸索出来的比较合适的用于检测效果的速度。
# 作者实际测得的速度大约15cm/s，因为Tell的精度没有那么高。
fSpeed = 117 / 10  # 移动的线速度

aSpeed = 360 / 10  # 旋转的角速度。10秒旋转一圈。也是讲者测出的经验数据，实际按50°/s来做。
interval = 0.25  # 也是讲者测出的经验数据，每间隔0.25秒检测一下按键信号？

dInterval = fSpeed * interval  # 在每个时间间隔里运行了多少距离
aInterval = aSpeed * interval  # 在每个时间间隔里转了多少角度
##############################

x, y = 500, 500  # 红色点的初始坐标
a = 0  # 无人机初始角度及累加后的角度
yaw = 0  # 无人机旋每次转的角度

# init的时候创建了一个400*400的pygame的窗口
kp.init()

me = tello.Tello()
me.connect()
print("无人机当前电量为：", me.get_battery())  # 查看无人机电量

points = [(0, 0), (0, 0)]


def getKeyboardInput():
    lr, fb, ud, yv = 0, 0, 0, 0  # lr:左右；fb：前后；ud：上下；yv：旋转角度
    speed = 15  # 线速度，和上面讲者给出的经验值15cm/s保持一致
    aspeed = 50  # 角速度，和上面讲者给出的经验值50°/s保持一致
    global x, y, yaw, a
    '''
    视频看到1小时30分时候感觉有点不太清楚讲者的意图。我理解是：
    1）lr, fb, ud, yv四个参数和KeyboardControl.py文件中的用法一样，通过send_rc_control来控制无人机的移动
    2）d, a 两个参数是用来控制画出来的红点的轨迹。
    '''

    d = 0  # 初始运行距离

    if kp.getKey('LEFT'):  # 向左
        lr = -speed
        d = dInterval
        a = -180  # sin(-90°)、sin(270°)、cos(180°)、cos(-180°)四个值都是-1


    elif kp.getKey('RIGHT'):  # 向右
        lr = speed
        d = -dInterval
        a = 180

    if kp.getKey('UP'):  # 前进
        fb = speed
        d = dInterval
        a = 270

    elif kp.getKey('DOWN'):  # 后退
        fb = -speed
        d = -dInterval
        a = -90

    # 上下移动的时候，红点的位置不改变，所以这里的代码和KeyboardControl.py中保持一致
    if kp.getKey('w'):
        ud = -speed
    elif kp.getKey('s'):
        ud = speed

    if kp.getKey('a'):
        yv = aspeed
        yaw -= aInterval  # 偏转的角度进行累加
    elif kp.getKey('d'):
        yv = -aspeed
        yaw += aInterval  # 偏转的角度进行累加

    if kp.getKey('q'):   me.land()
    if kp.getKey('e'):   me.takeoff()

    time.sleep(interval)
    a += yaw  # 每次旋转后，都进行角度累加
    # sin(-90°)、sin(270°)、cos(180°)、cos(-180°)四个值都是-1
    x += int(d * math.cos(math.radians(a)))
    y += int(d * math.sin(math.radians(a)))

    return [lr, fb, ud, yv, x, y]


def drawPoints(img, points):
    for point in points:
        # 在img的point位置上画一个半径5mm的红色圆。把列表points中所有的位置都画上点，形成轨迹。
        # opencv里表示颜色用的是BGR,而非GRG，所以画红圈用(0, 0, 255)
        cv2.circle(img, point, 5, (0, 0, 255), cv2.FILLED)
    cv2.circle(img, points[-1], 8, (0, 255, 0), cv2.FILLED)  # 绿色
    # 把坐标显示在底图上。只显示最后一个点的坐标，所以用points[-1]，这个元素本身是一个（x,y）坐标，所以用（points[-1][0]和points[-1][1]表示这个坐标值）；
    # 500是因为起始点是(500,500)，除以100是把单位转换成米
    # 在(points[-1][0]+10, points[-1][1]+30) 位置显示坐标，这样就不会和点重合了
    cv2.putText(img, f'({(points[-1][0] - 500) / 100},{(points[-1][1] - 500) / 100})m',
                (points[-1][0] + 10, points[-1][1] + 30), cv2.FONT_HERSHEY_PLAIN, 1, (255, 0, 255), 1)


while True:
    # 按按键的时候，鼠标应该点在pygame创建的窗口里。
    vals = getKeyboardInput()
    # 从作者在mapping那一节的讲解看，send_rc_control移动距离的单位是cm
    me.send_rc_control(vals[0], vals[1], vals[2], vals[3])

    '''
    使用Numpy创建纯色图片  参考：https://blog.csdn.net/Gskull/article/details/81105627     
    关于图像三通道和单通道的解释：  https://blog.csdn.net/qq_32211827/article/details/56854985   
    numpy是一个数学库，这里用来创建图片（大小是1000行1000列的用0填充的矩阵），“3”表示3通道图片。
    np.uint8代表2的8次方，也就是256，可以用来表示RGB。没深究。
    把下面的img 换成 img = cv2.imread('imgLena.jpg') 也可以，在imgLena.jpg上画了一个红点。
    '''
    img = np.zeros((1000, 1000, 3), np.uint8)
    # img = cv2.imread('imgLena.jpg')

    if (points[-1][0] != vals[4] or points[-1][1] != vals[5]):  # 如果没有按键盘，就不要把一个静止的点反复加入列表了
        points.append((vals[4], vals[5]))  # 注意这里的写法，直接把一个（x,y）坐标值添加到列表中

    drawPoints(img, points)
    cv2.imshow("Output", img)
    cv2.waitKey(1)
