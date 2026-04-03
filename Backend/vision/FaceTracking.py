'''
* @par          Copyright (C): 2023- , Qin
* @file         FaceTracking.py
* @author       Qin
* @version      V1.0
* @date         2023.03.19
* @brief        基于无人机实现人脸追踪
* @details      2023年4月3日测试了一下，运行效果和预期差别很大。有可能是程序写的有问题，也有可能是里面的一些参数需要调。
* @par History
'''

from djitellopy import tello
import cv2
import numpy as np
import time

img_w, img_h = 360, 240 # 图像的的宽和高，resize时候用

fbRange = [6200, 6800]  # 设置一个列表，存储触发前进或后退的2个阈值。这2个数字没说怎么来的，应该是经验值。

# 英文讲解停的不是很明白（2小时19分45秒），第一个0.4好像是比例（P值），第二个0.4（说是d值，好像是导数derivative）和第三个0（说是i值）没听明白是什么。讲师也没有说为什么使用这三个数值。
# 讲师说如果纠偏效果不好，可以自己调试这里的参数，但通常需要很长时间的调试。
pid = [0.4, 0.4, 0]

pError = 0

me = tello.Tello() #创建一个Tello对象，叫做me
me.connect() # 与无人机连接 TCP/UDP连接的相关过程都封装在里面了。
print("无人机当前电量为：", me.get_battery()) # 查看无人机电量
streamonState = me.streamon() # 开启无人机摄像机
print('streamon State is:', streamonState )
me.takeoff()

# 起飞后在默认高度的基础上再按25的速度上升3秒，以便能达到人脸的高度
me.send_rc_control(0, 0, 25, 0)
time.sleep(3)
me.send_rc_control(0, 0, 0, 0) # 避免无人机一直上升。讲师的代码里没有这一句，我自己加的。


'''
* Function       	findFace
* @author        	Qin
* @date          	2023.03.19
* @brief         	在图片img中找到脸.
* @details 	        这里用到的“haarcascade_frontalface_default.xml” 是一个国外牛人写的开源计算机视觉库，被收录在opencv里面。视频说可以在opencv官网中下载到。
                    安装过Opencv这个库后，这个xml文件可以直接在电脑上找到，按视频中放入项目文件夹下面即可。参考：https://blog.csdn.net/weixin_43352501/article/details/119878166
                    如果要做人脸识别还有其它的库辅助，参考：https://blog.csdn.net/qq_40985985/article/details/118254878
                    从讲师的个人网站下载了全套库文件，放在压缩包“haarcascades.zip”里。
* @param[]	
* @retval        	
* @par History   	
'''


def findFace(img):
    faceCascade = cv2.CascadeClassifier("Resource/haarcascade_frontalface_default.xml")

    # 先把图像变成灰度，然后检测人脸。讲师说在他专门的OpenCV教学视频中有讲解。
    imgGray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 1.2和8这两个参数是讲师的经验值，如果识别效果不好的话可以自行调整。没有仔细去了解detectMultiScale这个函数，视频说会返回(x,y,w,h)四个值，也就是下面for循环用到的。
    # (x, y, w, h)是框住人脸的长方形起点位置的坐标以及长方形的宽、高
    # 有的python内置函数怎么就一个pass（比如下面的detectMultiScale）：
    # python的内置函数都是内嵌在解释器里面的，是使用C编写的，正常情况下你是无法查看的，只不过pycharm这种智能编辑器对其进行了一个抽象罢了，可以让你查看相应的注释。
    # https://www.zhihu.com/question/61353466
    # 从Jupyter的cell“测试ChatGPT写的识别一张图片中多个人脸的代码”看出detectMultiScale的返回值是一个列表。
    faces = faceCascade.detectMultiScale(imgGray, 1.2, 8)

    # 创建2个列表，找img中面积最大的那张脸，认为那是靠摄像机最近的，也就是我们要找的。
    myFaceListC = []  # C表示中心center，用来存储所有脸部中心（x,y）坐标值，用来控制无人机旋转。
    myFaceListArea = []  # 用来存储所有框住脸部的长方形面积，用来决定无人机前进还是后退。

    for (x, y, w, h) in faces:
        # 画出围绕脸部的矩形。（x,y）:矩形的左上角起点；（w,h）：矩形的宽和高， (0, 0, 255)：矩形边框红色；2：矩形边框宽度为2
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 0, 255), 2)

        # 获取矩形的中心点。‘//’ 表示得到的得数向下取整。
        cx = x + ( w // 2 )
        cy = y + ( y // 2 )

        # 框住脸部的矩形的面积。
        area = w * h

        # 在矩形的中心点画一个半径5cm的实心绿点
        cv2.circle(img, (cx, cy), 5, (0, 255, 0), cv2.FILLED)

        myFaceListC.append([cx, cy])
        myFaceListArea.append(area)

    if len(myFaceListC) != 0:  # 判断列表是否为空
        i = myFaceListArea.index(max(myFaceListArea))  # 找到面积最大的那张脸在列表中的索引

        # 返回整张图像、图像中最大那张脸矩形的中心点和面积（用[]括起来，也就是返回了一个列表）
        # 把传到函数里的img再返回出去，最终形成在电脑上显示的连续的视频流。

        return img, [myFaceListC[i], myFaceListArea[i]]
    else:
        return img, [[0, 0], 0]


'''
* Function       	trackFace
* @author        	Qin
* @date          	2023.03.27
* @brief         	跟踪找到的脸.
* @details          相对于视频教程，这里对函数中参数进行了重新命名，避免误解。
* @param[]	        
* @retval        	
* @par History   	
'''
def trackFace(me, info, img_w, pid, pError):
#def trackFace(info, w, pid, pError):
    c_x, c_y = info[0] # c_x, c_y是长方形的中心坐标。注意这种写法，info[0]这个列表元素本身也是一个列表，myFaceListC.append([cx, cy])
    area = info[1]
    fb = 0 # 前进后退的速度

    # 人脸中央和图像中央的偏离值，实际上也就是人脸中央和无人机镜头的偏离值。
    error = c_x - (img_w // 2)

    '''
    讲师说这里不详细讲pid工作原理，也不是很有必要了解，感兴趣可以去youtube上去找视频了解pid的工作原理。
    通过调整pid的值来调整无人机修正位置的灵敏度。
    speed 是旋转速度
    '''
    speed = pid[0] * error + pid[1] * (error - pError)
    speed = int(np.clip(speed, -100, 100))  # 把无人机旋转速度限制在-100~100之间。

    # 无人机靠人近了就后退反之前进，距离适当的话保持静止
    if area > fbRange[0] and area < fbRange[1]:
        fb = 0
    elif area > fbRange[1]:
        fb = 20
    elif area < fbRange[0] and area != 0:
        fb = -20

    # 下面这个if好像是在没有发现人脸的时候让无人机不要旋转。
    if c_x == 0:
        speed = 0
        error = 0 # 偏离度为0

    #print("speed is:",speed,"fb is:",fb)

    me.send_rc_control(0, fb, 0, speed)  #  调整前进/后退 和 旋转角度

    return error # 2小时21分45秒。说是为了赋值为pError（上一个偏移），以便下次使用pError。

# 教学视频用的是1表示usb外接的摄像头，我这里用0表示使用电脑自带摄像头。见jupyter文件中”测试电脑自带摄像头“cell。
# 第二个参数用来解决这个报错：cap_msmf.cpp (435) `anonymous-namespace'::SourceReaderCB::~SourceReaderCB terminating async callback
#cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

while True:
    #_, img = cap.read()  # 必须用2个参数来接返回值，参考cell”测试电脑自带摄像头“
    img = me.get_frame_read().frame  # img是一帧图像，也就是一个图片
    img, info = findFace(img)

    # 在脸上画的方框和圆点不受resize的影响，resize后detectMultiScale返回的坐标值也跟着变了。
    img = cv2.resize(img,(img_w,img_h))

    pError = trackFace(me, info, img_w, pid, pError)
    #pError = trackFace(info, w, pid, pError)
    #print("Center:", info[0], "Area:", info[1])


    cv2.imshow("ouput", img)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        me.land()
        break # 结束while循环
