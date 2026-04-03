import pygame

# 初始化，产生一个窗口。所有的按键检测都要在Pygame的窗口内进行，所以这里要创建窗口
def init():
    pygame.init()
    win = pygame.display.set_mode((400, 400))

# 检测按键是否被按下。如果keyName按下了，返回Ture，反之返回False。这个函数是固定写法，不用详细看。
# 侯老师飞机大战里也有检测按键的函数，可以对比看一下。
def getKey(keyName):
    ans = False
    for eve in pygame.event.get(): pass
    keyInput = pygame.key.get_pressed()
    myKey = getattr(pygame, 'K_{}'.format(keyName)) # 固定写法，没看懂
    if keyInput[myKey]:
        ans = True
    pygame.display.update()
    return ans

def main():
    print(getKey('a')) #（1）输入法切换成英文；（2）鼠标放在窗口里面——不能放在顶部条幅上——持续按下左键。未按时显示False，按下后显示True

if __name__ == '__main__': #意味着这个文件是主文件
    init()
    while True:
        main()