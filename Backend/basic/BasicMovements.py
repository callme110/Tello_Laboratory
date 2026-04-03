from djitellopy import tello
from time import sleep

me = tello.Tello()  # 创建一个Tello对象，叫做me
me.connect()  # 与无人机连接 TCP/UDP连接的相关过程都封装在里面了。

print("无人机当前电量为：", me.get_battery())  # 查看无人机电量

'''
如果只执行tekeoff然后维持原地悬停状态5秒，然后降落，其它的代码都注释掉，实际情况是:
1)无人机经常不是垂直起飞，有时候接近垂直起飞，有时候起飞的时候会一下子偏离很多；
2）有时候在飞行过程中会自己进行位置偏移，偶尔也会抬升高度，但基本不会转向；
3）有时候会5秒后就降落，有时候会过很长时间才降落，降落之前不知道是不是在计算对地距离。
4）无人机底部的2个“灯”只有一个是亮的。
上述情况不知道是不是属于故障，有时间上网查查或者问一下大疆的售后。
'''
me.takeoff()
sleep(5)

# 控制无人机的4维运动。参考腾讯文档。按住Ctrl点击send_rc_control查看函数定义
# send_rc_control中4个参数是做某个特定动作的速度，范围都是-100 ~ 100，持续时间为0.5秒。
# send_rc_control函数定义中：TIME_BTW_RC_CONTROL_COMMANDS = 0.5  # in seconds

'''
me.send_rc_control(0, 50, 0, 0)   # 向前（有摄像头的位置为头部）按50的速度前进
sleep(3) # 移动后，维持原地悬停状态3秒

me.send_rc_control(30, 0, 0, 0)  # 站在无人机尾部看，无人机向右按30的速度偏移
sleep(3) # 移动后，维持原地悬停状态3秒


me.send_rc_control(0, 0, 0, 90)  # 从无人机上方向下看，无人机顺时针按90的速度旋转
sleep(3) # 移动后，维持原地悬停状态3秒
'''

# 在降落前，强制无人机进入原地悬停状态状态。
me.send_rc_control(0, 0, 0, 0)
me.land()
