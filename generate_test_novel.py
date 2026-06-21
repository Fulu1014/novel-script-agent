import random

def generate_web_novel():
    filename = "./测试/网文极限测试样本.txt"
    
    # 网文常见的正文废话库
    paragraphs = [
        "他倒吸一口凉气，眼神中闪过一丝不可思议。此子的恐怖如斯，断不可留！",
        "周围的人群爆发出阵阵惊呼，谁能想到，一个连斗之气三段都没有的废物，竟然敢顶撞大长老？",
        "“呵呵，既然你找死，那就怪不得我了。”黑衣人冷笑一声，手中的长剑猛然化作一道流光。",
        "夜色如水，他在床榻上盘膝而坐，体内那股神秘的力量再次开始运转，冲击着经脉的瓶颈。",
        "就在这时，天空骤然变得暗沉，一股远古洪荒般的气息从大地的裂缝中喷涌而出！"
    ]
    
    with open(filename, 'w', encoding='utf-8') as f:
        # 书名与乱七八糟的前言
        f.write("《剑灭苍穹》\n作者：神秘大神\n\n")
        f.write("本书首发于某某中文网，未经授权禁止转载！\n")
        f.write("前言/楔子\n\n    神历一万年，诸神陨落......\n\n")
        
        for i in range(1, 51):
            # 模拟网文千奇百怪的章节标题格式
            rand_format = random.randint(1, 4)
            if rand_format == 1:
                f.write(f"\n第{i}章 恐怖如斯\n")  # 标准阿拉伯数字
            elif rand_format == 2:
                f.write(f"\n第{i}章\n")        # 纯数字无标题
            elif rand_format == 3:
                f.write(f"\nChapter {i} 绝地反击\n") # 英文洋气版
            else:
                f.write(f"\n第{i}章：逆天改命\n") # 冒号版
            
            # 模拟网文极其细碎的段落（每章写几段废话）
            for _ in range(random.randint(5, 10)):
                f.write(random.choice(paragraphs) + "\n\n")
            
            # 模拟网文最让人头疼的“噪音”（作者拉票）
            if random.random() > 0.5:
                f.write("【作者的话：今天卡文了，只有一更。大家手里有月票的投一下啊！求推荐！求收藏！】\n\n")
            if random.random() > 0.8:
                f.write("感谢“XX盟主”打赏的10000书币！老板大气！\n\n")

    print(f"✅ 生成成功！文件已保存为：{filename}")

if __name__ == "__main__":
    generate_web_novel()