'''
* @par
* @file         ImageCapture.py
* @author
* @version
* @date
* @brief        从Tello的摄像机捕获图像，输出的是连续的视频流
* @details      可参考：https://zhuanlan.zhihu.com/p/367091136
* @par History
'''

from djitellopy import tello
import cv2

me = tello.Tello()  # 创建一个Tello对象，叫做me
me.connect()  # 与无人机连接 TCP/UDP连接的相关过程都封装在里面了。

print("无人机当前电量为：", me.get_battery())  # 查看无人机电量

# streamon产生有很多帧组成的图像数据流，后面用while进行处理。
streamonState = me.streamon()
print('streamon State is:', streamonState )

# 下面While执行下来看到的是实时视频流，不是一张一张的图片，因为下面每张图片之停留1ms，所以连贯性很好。
while True:
    img = me.get_frame_read().frame  # img是一帧图像，也就是一个图片
    img = cv2.resize(img, (360, 240))
    cv2.imshow("Image", img)  # 创建一个窗口来显示图片，第一个参数是窗口的名称
    cv2.waitKey(1) # 做一个1ms延时，否则看不到图片