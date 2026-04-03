'''
* @par          Copyright (C): 2023- , Qin
* @file         ColorPicker.py
* @author       Qin
* @version      V1.0
* @date         2023.03.27
* @brief        用来挑选颜色
* @details      这个文件的代码是直接从讲师个人网站下载的。
                视频2小时49分13秒讲这个代码，可以粗略看懂什么意思，详细了解代码的话可能要返回头看讲师OpenCV的视频。
* @par History

'''

import cv2
import numpy as np
from djitellopy import tello

frameWidth = 480

frameHeight = 360

# me = tello.Tello()

# me.connect()

# print(me.get_battery())

# me.streamon()

'''
* Function       	empty
* @author        	讲师
* @date          	未知
* @brief            一个空函数。
* @details 	        给cv2.createTrackbar用的，不做任何事情。                 
* @param[]          
* @retval           
* @par History
'''


def empty(a):
    pass


# 创建一个窗口，上面右6个可拖动的滚动条。
cv2.namedWindow("HSV")

cv2.resizeWindow("HSV", 640, 240)

cv2.createTrackbar("HUE Min", "HSV", 0, 179, empty)

cv2.createTrackbar("HUE Max", "HSV", 179, 179, empty)

cv2.createTrackbar("SAT Min", "HSV", 0, 255, empty)

cv2.createTrackbar("SAT Max", "HSV", 255, 255, empty)

cv2.createTrackbar("VALUE Min", "HSV", 0, 255, empty)

cv2.createTrackbar("VALUE Max", "HSV", 255, 255, empty)

# 使用电脑自带摄像头捕获视频
cap = cv2.VideoCapture(0)

frameCounter = 0

while True:

    # img = me.get_frame_read().frame

    _, img = cap.read()

    img = cv2.resize(img, (frameWidth, frameHeight))

    # img = cv2.flip(img,0)

    # 把原始图片转换成HSV图片
    imgHsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # 白底黑纹转换
    # imgHsv = 255-imgHsv
    # 获取6个滑动条的数据
    h_min = cv2.getTrackbarPos("HUE Min", "HSV")

    h_max = cv2.getTrackbarPos("HUE Max", "HSV")

    s_min = cv2.getTrackbarPos("SAT Min", "HSV")

    s_max = cv2.getTrackbarPos("SAT Max", "HSV")

    v_min = cv2.getTrackbarPos("VALUE Min", "HSV")

    v_max = cv2.getTrackbarPos("VALUE Max", "HSV")

    # 形成lower和upper两个数组
    lower = np.array([h_min, s_min, v_min])

    upper = np.array([h_max, s_max, v_max])

    # cv2.inRange函数 参考：https://blog.csdn.net/hjxu2016/article/details/77834599
    # 在lower,upper以外的数值全部变成0，lower,upper之间的全部变成255
    # 这样mask不一定是一个黑白两色，参考：https://blog.csdn.net/weixin_48249563/article/details/114003012。这个链接中要分理出蓝色，因此过程中产生的就不是黑白两色图片。
    # 通过滑动滑动条，让赛道变成白色，赛道意外全部变成黑色，从而获得需要的掩膜数据(mask)，也就是lower,upper两个数组的值。也就是我们获取的是只保留白色的掩膜。
    mask = cv2.inRange(imgHsv, lower, upper)

    # 把掩膜mask以外的内容全部变成黑色。掩膜覆盖到的地方保留接近原色。
    # 参考：https://blog.csdn.net/lukas_ten/article/details/115149086
    result = cv2.bitwise_and(img, img, mask=mask)

    # 把组成lower,upper两个数组的6个值打印出来。
    print(f'[{h_min},{s_min},{v_min},{h_max},{s_max},{v_max}]')

    # cv2.COLOR_GRAY2BGR从视觉上来说，不是把灰度图变成了现实世界中的彩色图，感觉指示灰度图（这个程序里是黑白的）的亮度更亮了一些。
    # 参考：https://zhuanlan.zhihu.com/p/73201428
    mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

    # hstack应该是显示3个图片，img是原图，mask是做了cv2.COLOR_GRAY2BGR的图，这里是黑白的；result是掩膜处理后的图，掩膜覆盖到的地方保留接近原色。
    hStack = np.hstack([img, mask, result])

    cv2.imshow('Horizontal Stacking', hStack)

    if cv2.waitKey(1) and 0xFF == ord('q'):
        break

cap.release()
#
cv2.destroyAllWind()
