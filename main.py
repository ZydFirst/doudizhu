from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import random
import time
import re
from typing import Dict, List, Tuple, Optional, Union

@register("doudizhu", "YourName", "一个简单的斗地主游戏插件，支持QQ群聊中进行游戏", "1.0.0")
class DouDiZhuPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 游戏状态：0-未开始，1-等待加入，2-游戏中
        self.game_status = {}
        # 玩家信息 {group_id: {player_id: player_name}}
        self.players = {}
        # 当前牌局 {group_id: {cards, current_player, landlord, last_play}}
        self.game_data = {}
        # 玩家手牌 {group_id: {player_id: [cards]}}
        self.player_cards = {}
        # 游戏计时
        self.game_time = {}
        # 牌面值映射
        self.card_values = {
            '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
            'J': 11, 'Q': 12, 'K': 13, 'A': 14, '2': 15, 'joker': 16, 'JOKER': 17
        }
        # 牌型
        self.card_types = {
            'single': 1,      # 单牌
            'pair': 2,        # 对子
            'trio': 3,        # 三张
            'trio_single': 4, # 三带一
            'trio_pair': 5,   # 三带二
            'straight': 6,    # 顺子
            'pairs': 7,       # 连对
            'plane': 8,       # 飞机
            'bomb': 9,        # 炸弹
            'rocket': 10      # 火箭
        }
        
    # 帮助命令
    @filter.command("斗地主帮助")
    async def doudizhu_help(self, event: AstrMessageEvent):
        """显示斗地主游戏帮助"""
        help_text = """斗地主游戏帮助：
1. 发送 '斗地主' 创建游戏
2. 发送 '加入' 加入游戏
3. 发送 '开始' 开始游戏
4. 叫分阶段：
   - 发送 '叫分 1/2/3' 叫分
   - 发送 '不叫' 不叫地主
5. 出牌阶段：
   - 发送 '出牌 牌1 牌2 ...' 出牌
   - 发送 '不出' 不出牌
   - 发送 '手牌' 查看自己的手牌
6. 其他命令：
   - 发送 '状态' 查看游戏状态
   - 发送 '结束游戏' 强制结束游戏

牌型说明：
- 单牌：任意单张牌
- 对子：两张相同点数的牌
- 三张：三张相同点数的牌
- 三带一：三张相同点数的牌 + 一张单牌
- 三带二：三张相同点数的牌 + 一对
- 顺子：五张或更多的连续单牌（不能包含2和王）
- 连对：三对或更多的连续对子（不能包含2和王）
- 飞机：两个或更多的连续三张（不能包含2和王）
- 炸弹：四张相同点数的牌
- 火箭：大小王

牌面表示：
- 花色：♠(黑桃) ♥(红桃) ♦(方块) ♣(梅花)
- 点数：3, 4, 5, 6, 7, 8, 9, 10, J, Q, K, A, 2
- 小王：joker
- 大王：JOKER

游戏规则：
- 三人游戏，一人为地主，两人为农民
- 地主先出牌，然后按顺序出牌
- 出牌必须大于上家出的牌
- 可以选择不出牌，但如果一轮中所有人都不出，则由最后出牌的玩家继续出牌
- 谁先出完所有牌，谁就获胜
- 如果地主获胜，地主得分为叫分的2倍，农民各扣叫分
- 如果农民获胜，农民各得叫分，地主扣叫分的2倍
"""
        yield event.plain_result(help_text)

    async def initialize(self):
        """插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        logger.info("斗地主插件已加载")

    # 开始游戏命令
    @filter.command("斗地主")
    async def start_game(self, event: AstrMessageEvent):
        """开始一局斗地主游戏"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否已经开始
        if group_id in self.game_status and self.game_status[group_id] != 0:
            yield event.plain_result(f"游戏已经在进行中，当前状态: {self._get_status_text(group_id)}")
            return
            
        # 初始化游戏
        self.game_status[group_id] = 1  # 等待加入状态
        self.players[group_id] = {user_id: user_name}
        self.game_time[group_id] = time.time()
        
        yield event.plain_result(f"{user_name} 发起了斗地主游戏！\n发送 '加入' 参与游戏，需要3名玩家。\n发起者已自动加入。\n发送 '开始' 开始游戏。")

    # 加入游戏命令
    @filter.command("加入")
    async def join_game(self, event: AstrMessageEvent):
        """加入斗地主游戏"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否处于等待加入状态
        if group_id not in self.game_status or self.game_status[group_id] != 1:
            yield event.plain_result("当前没有等待加入的游戏，请先发送 '斗地主' 开始一局游戏")
            return
            
        # 检查玩家是否已经加入
        if user_id in self.players[group_id]:
            yield event.plain_result(f"{user_name} 已经在游戏中了")
            return
            
        # 检查玩家数量是否已满
        if len(self.players[group_id]) >= 3:
            yield event.plain_result("游戏人数已满（3人），无法加入")
            return
            
        # 加入游戏
        self.players[group_id][user_id] = user_name
        
        yield event.plain_result(f"{user_name} 加入了游戏！当前玩家数: {len(self.players[group_id])}/3")

    # 开始游戏命令
    @filter.command("开始")
    async def begin_game(self, event: AstrMessageEvent):
        """开始斗地主游戏"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否处于等待加入状态
        if group_id not in self.game_status or self.game_status[group_id] != 1:
            yield event.plain_result("当前没有等待加入的游戏，请先发送 '斗地主' 开始一局游戏")
            return
            
        # 检查玩家数量是否足够
        if len(self.players[group_id]) < 3:
            yield event.plain_result(f"玩家数量不足，需要3名玩家，当前只有{len(self.players[group_id])}名玩家")
            return
            
        # 开始游戏
        self.game_status[group_id] = 2  # 游戏中状态
        
        # 初始化游戏数据
        self._init_game(group_id)
        
        # 发牌
        self._deal_cards(group_id)
        
        # 通知玩家手牌
        yield event.plain_result("游戏开始！正在私聊发送手牌...")
        
        # 发送手牌信息给每个玩家
        for player_id, player_name in self.players[group_id].items():
            cards_str = self._format_cards(self.player_cards[group_id][player_id])
            # 这里应该是私聊发送，但示例中简化为群聊发送
            yield event.plain_result(f"[私聊] {player_name} 的手牌:\n{cards_str}")
        
        # 开始抢地主
        self.game_data[group_id]['bid_stage'] = True
        self.game_data[group_id]['bid_score'] = 0
        self.game_data[group_id]['bid_player'] = None
        
        # 随机选择一个玩家开始抢地主
        player_ids = list(self.players[group_id].keys())
        start_player = random.choice(player_ids)
        self.game_data[group_id]['current_player'] = start_player
        
        yield event.plain_result(f"请 {self.players[group_id][start_player]} 开始叫分 (1-3分)，回复 '叫分 数字' 或 '不叫'")

    # 叫分命令
    @filter.command("叫分")
    async def bid_score(self, event: AstrMessageEvent):
        """叫地主分数"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        message_str = event.message_str
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否在进行中
        if group_id not in self.game_status or self.game_status[group_id] != 2:
            yield event.plain_result("当前没有进行中的游戏")
            return
            
        # 检查是否在抢地主阶段
        if not self.game_data[group_id].get('bid_stage', False):
            yield event.plain_result("当前不是抢地主阶段")
            return
            
        # 检查是否轮到该玩家
        if self.game_data[group_id]['current_player'] != user_id:
            yield event.plain_result(f"当前轮到 {self.players[group_id][self.game_data[group_id]['current_player']]} 叫分")
            return
            
        # 解析叫分
        score_match = re.search(r'叫分\s*(\d+)', message_str)
        if not score_match:
            yield event.plain_result("请正确输入叫分，格式为 '叫分 数字'")
            return
            
        score = int(score_match.group(1))
        
        # 检查分数是否有效
        if score < 1 or score > 3:
            yield event.plain_result("叫分必须在1-3分之间")
            return
            
        # 检查分数是否高于当前最高分
        if score <= self.game_data[group_id]['bid_score']:
            yield event.plain_result(f"叫分必须高于当前最高分 {self.game_data[group_id]['bid_score']}")
            return
            
        # 更新叫分信息
        self.game_data[group_id]['bid_score'] = score
        self.game_data[group_id]['bid_player'] = user_id
        
        # 如果叫3分，直接成为地主
        if score == 3:
            yield from self._end_bidding(event, group_id)
            return
            
        # 轮到下一个玩家
        self._next_player(group_id)
        
        yield event.plain_result(f"{user_name} 叫了 {score} 分！\n请 {self.players[group_id][self.game_data[group_id]['current_player']]} 叫分，回复 '叫分 数字' 或 '不叫'")

    # 不叫命令
    @filter.command("不叫")
    async def no_bid(self, event: AstrMessageEvent):
        """不叫地主"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否在进行中
        if group_id not in self.game_status or self.game_status[group_id] != 2:
            yield event.plain_result("当前没有进行中的游戏")
            return
            
        # 检查是否在抢地主阶段
        if not self.game_data[group_id].get('bid_stage', False):
            yield event.plain_result("当前不是抢地主阶段")
            return
            
        # 检查是否轮到该玩家
        if self.game_data[group_id]['current_player'] != user_id:
            yield event.plain_result(f"当前轮到 {self.players[group_id][self.game_data[group_id]['current_player']]} 叫分")
            return
            
        # 轮到下一个玩家
        self._next_player(group_id)
        
        # 如果所有玩家都不叫，或者回到了第一个叫分的玩家
        if self.game_data[group_id]['current_player'] == self.game_data[group_id].get('first_bidder'):
            # 如果没有人叫分，重新发牌
            if self.game_data[group_id]['bid_score'] == 0:
                yield event.plain_result("没有人叫分，重新发牌！")
                self._init_game(group_id)
                self._deal_cards(group_id)
                
                # 通知玩家手牌
                yield event.plain_result("重新发牌！正在私聊发送手牌...")
                
                # 发送手牌信息给每个玩家
                for player_id, player_name in self.players[group_id].items():
                    cards_str = self._format_cards(self.player_cards[group_id][player_id])
                    # 这里应该是私聊发送，但示例中简化为群聊发送
                    yield event.plain_result(f"[私聊] {player_name} 的手牌:\n{cards_str}")
                
                # 开始抢地主
                self.game_data[group_id]['bid_stage'] = True
                self.game_data[group_id]['bid_score'] = 0
                self.game_data[group_id]['bid_player'] = None
                
                # 随机选择一个玩家开始抢地主
                player_ids = list(self.players[group_id].keys())
                start_player = random.choice(player_ids)
                self.game_data[group_id]['current_player'] = start_player
                self.game_data[group_id]['first_bidder'] = start_player
                
                yield event.plain_result(f"请 {self.players[group_id][start_player]} 开始叫分 (1-3分)，回复 '叫分 数字' 或 '不叫'")
                return
            else:
                # 结束叫分阶段
                yield from self._end_bidding(event, group_id)
                return
        
        yield event.plain_result(f"{user_name} 不叫！\n请 {self.players[group_id][self.game_data[group_id]['current_player']]} 叫分，回复 '叫分 数字' 或 '不叫'")

    # 出牌命令
    @filter.command("出牌")
    async def play_cards(self, event: AstrMessageEvent):
        """出牌"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        message_str = event.message_str
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否在进行中
        if group_id not in self.game_status or self.game_status[group_id] != 2:
            yield event.plain_result("当前没有进行中的游戏")
            return
            
        # 检查是否在出牌阶段
        if self.game_data[group_id].get('bid_stage', True):
            yield event.plain_result("当前不是出牌阶段")
            return
            
        # 检查是否轮到该玩家
        if self.game_data[group_id]['current_player'] != user_id:
            yield event.plain_result(f"当前轮到 {self.players[group_id][self.game_data[group_id]['current_player']]} 出牌")
            return
            
        # 解析出牌
        cards_match = re.search(r'出牌\s*(.+)', message_str)
        if not cards_match:
            yield event.plain_result("请正确输入出牌，格式为 '出牌 牌1 牌2 ...'")
            return
            
        cards_str = cards_match.group(1).strip()
        cards = self._parse_cards(cards_str)
        
        # 检查牌是否在玩家手中
        if not self._has_cards(group_id, user_id, cards):
            yield event.plain_result("您的手牌中没有这些牌")
            return
            
        # 检查牌型是否合法
        card_type, card_value = self._get_card_type(cards)
        if card_type is None:
            yield event.plain_result("出牌不符合规则，请重新出牌")
            return
            
        # 检查是否符合上一手牌的规则
        last_play = self.game_data[group_id].get('last_play', None)
        if last_play and not self._can_beat(card_type, card_value, last_play['type'], last_play['value']):
            yield event.plain_result(f"您的牌无法大过上一手牌，请重新出牌或选择 '不出'")
            return
            
        # 出牌
        self._remove_cards(group_id, user_id, cards)
        
        # 更新最后一手牌
        self.game_data[group_id]['last_play'] = {
            'player': user_id,
            'cards': cards,
            'type': card_type,
            'value': card_value
        }
        
        # 检查是否获胜
        if len(self.player_cards[group_id][user_id]) == 0:
            # 游戏结束，当前玩家获胜
            landlord = self.game_data[group_id]['landlord']
            is_landlord_win = (user_id == landlord)
            
            # 计算分数
            base_score = self.game_data[group_id]['bid_score']
            
            # 输出结果
            result = f"游戏结束！{user_name} 获胜！\n"
            if is_landlord_win:
                result += f"地主胜利！地主得分：+{base_score * 2}，农民得分：-{base_score}\n"
            else:
                result += f"农民胜利！农民得分：+{base_score}，地主得分：-{base_score * 2}\n"
                
            # 重置游戏状态
            self.game_status[group_id] = 0
            
            yield event.plain_result(result)
            return
            
        # 轮到下一个玩家
        self._next_player(group_id)
        
        # 输出结果
        result = f"{user_name} 出牌：{self._format_cards(cards)}\n"
        result += f"剩余 {len(self.player_cards[group_id][user_id])} 张牌\n"
        result += f"请 {self.players[group_id][self.game_data[group_id]['current_player']]} 出牌"
        
        yield event.plain_result(result)

    # 不出命令
    @filter.command("不出")
    async def pass_play(self, event: AstrMessageEvent):
        """不出牌"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否在进行中
        if group_id not in self.game_status or self.game_status[group_id] != 2:
            yield event.plain_result("当前没有进行中的游戏")
            return
            
        # 检查是否在出牌阶段
        if self.game_data[group_id].get('bid_stage', True):
            yield event.plain_result("当前不是出牌阶段")
            return
            
        # 检查是否轮到该玩家
        if self.game_data[group_id]['current_player'] != user_id:
            yield event.plain_result(f"当前轮到 {self.players[group_id][self.game_data[group_id]['current_player']]} 出牌")
            return
            
        # 检查是否可以不出
        last_play = self.game_data[group_id].get('last_play', None)
        if last_play is None or last_play['player'] == user_id:
            yield event.plain_result("您必须出牌")
            return
            
        # 轮到下一个玩家
        self._next_player(group_id)
        
        # 输出结果
        result = f"{user_name} 不出\n"
        result += f"请 {self.players[group_id][self.game_data[group_id]['current_player']]} 出牌"
        
        yield event.plain_result(result)

    # 查看手牌命令
    @filter.command("手牌")
    async def show_cards(self, event: AstrMessageEvent):
        """查看手牌"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否在进行中
        if group_id not in self.game_status or self.game_status[group_id] != 2:
            yield event.plain_result("当前没有进行中的游戏")
            return
            
        # 检查玩家是否在游戏中
        if user_id not in self.players[group_id]:
            yield event.plain_result("您不在当前游戏中")
            return
            
        # 获取手牌
        cards = self.player_cards[group_id][user_id]
        cards_str = self._format_cards(cards)
        
        # 输出结果
        result = f"[私聊] {user_name} 的手牌:\n{cards_str}"
        
        yield event.plain_result(result)

    # 查看游戏状态命令
    @filter.command("状态")
    async def show_status(self, event: AstrMessageEvent):
        """查看游戏状态"""
        group_id = event.get_group_id()
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否存在
        if group_id not in self.game_status:
            yield event.plain_result("当前没有游戏")
            return
            
        # 获取游戏状态
        status = self._get_status_text(group_id)
        
        # 输出结果
        result = f"当前游戏状态: {status}\n"
        
        if self.game_status[group_id] == 1:
            # 等待加入状态
            result += f"已加入玩家: {', '.join(self.players[group_id].values())}\n"
            result += f"玩家数: {len(self.players[group_id])}/3\n"
            result += "发送 '加入' 参与游戏，发送 '开始' 开始游戏"
        elif self.game_status[group_id] == 2:
            # 游戏中状态
            if self.game_data[group_id].get('bid_stage', False):
                # 叫分阶段
                result += f"当前叫分: {self.game_data[group_id]['bid_score']}\n"
                if self.game_data[group_id]['bid_score'] > 0:
                    bid_player = self.players[group_id][self.game_data[group_id]['bid_player']]
                    result += f"当前最高叫分者: {bid_player}\n"
                result += f"当前轮到: {self.players[group_id][self.game_data[group_id]['current_player']]}\n"
                result += "请使用 '叫分 数字' 或 '不叫' 进行操作"
            else:
                # 出牌阶段
                landlord = self.players[group_id][self.game_data[group_id]['landlord']]
                result += f"地主: {landlord}\n"
                result += f"当前轮到: {self.players[group_id][self.game_data[group_id]['current_player']]}\n"
                
                # 显示上一手牌
                last_play = self.game_data[group_id].get('last_play', None)
                if last_play:
                    last_player = self.players[group_id][last_play['player']]
                    last_cards = self._format_cards(last_play['cards'])
                    result += f"上一手牌 ({last_player}): {last_cards}\n"
                
                result += "请使用 '出牌 牌1 牌2 ...' 或 '不出' 进行操作\n"
                result += "发送 '手牌' 查看自己的手牌"
        
        yield event.plain_result(result)

    # 结束游戏命令
    @filter.command("结束游戏")
    async def end_game(self, event: AstrMessageEvent):
        """强制结束游戏"""
        group_id = event.get_group_id()
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        
        # 检查是否在群聊中
        if not group_id:
            yield event.plain_result("斗地主游戏仅支持在群聊中进行")
            return
            
        # 检查游戏是否存在
        if group_id not in self.game_status or self.game_status[group_id] == 0:
            yield event.plain_result("当前没有进行中的游戏")
            return
            
        # 重置游戏状态
        self.game_status[group_id] = 0
        
        yield event.plain_result(f"{user_name} 强制结束了游戏")

    # 辅助方法：初始化游戏
    def _init_game(self, group_id):
        """初始化游戏数据"""
        self.game_data[group_id] = {
            'cards': self._create_cards(),
            'current_player': None,
            'landlord': None,
            'last_play': None,
            'bid_stage': True,
            'bid_score': 0,
            'bid_player': None
        }
        self.player_cards[group_id] = {player_id: [] for player_id in self.players[group_id]}

    # 辅助方法：创建一副牌
    def _create_cards(self):
        """创建一副牌"""
        suits = ['♠', '♥', '♦', '♣']
        ranks = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
        cards = [f"{suit}{rank}" for suit in suits for rank in ranks]
        cards.append('joker')  # 小王
        cards.append('JOKER')  # 大王
        random.shuffle(cards)  # 洗牌
        return cards

    # 辅助方法：发牌
    def _deal_cards(self, group_id):
        """发牌"""
        cards = self.game_data[group_id]['cards']
        player_ids = list(self.players[group_id].keys())
        
        # 每人17张牌
        for i, player_id in enumerate(player_ids):
            self.player_cards[group_id][player_id] = sorted(cards[i*17:(i+1)*17], key=self._card_sort_key)
        
        # 剩余3张作为地主牌
        self.game_data[group_id]['landlord_cards'] = cards[51:]

    # 辅助方法：结束叫分阶段
    async def _end_bidding(self, event, group_id):
        """结束叫分阶段"""
        # 设置地主
        landlord_id = self.game_data[group_id]['bid_player']
        self.game_data[group_id]['landlord'] = landlord_id
        
        # 地主获得底牌
        landlord_cards = self.game_data[group_id]['landlord_cards']
        self.player_cards[group_id][landlord_id].extend(landlord_cards)
        self.player_cards[group_id][landlord_id] = sorted(self.player_cards[group_id][landlord_id], key=self._card_sort_key)
        
        # 结束叫分阶段
        self.game_data[group_id]['bid_stage'] = False
        
        # 地主先出牌
        self.game_data[group_id]['current_player'] = landlord_id
        
        # 输出结果
        landlord_name = self.players[group_id][landlord_id]
        score = self.game_data[group_id]['bid_score']
        
        result = f"{landlord_name} 成为地主，分数：{score}分！\n"
        result += f"地主牌：{self._format_cards(landlord_cards)}\n"
        result += f"请 {landlord_name} 出牌"
        
        # 更新地主的手牌信息
        cards_str = self._format_cards(self.player_cards[group_id][landlord_id])
        yield event.plain_result(f"[私聊] {landlord_name} 的手牌更新:\n{cards_str}")
        
        yield event.plain_result(result)

    # 辅助方法：下一个玩家
    def _next_player(self, group_id):
        """轮到下一个玩家"""
        player_ids = list(self.players[group_id].keys())
        current_index = player_ids.index(self.game_data[group_id]['current_player'])
        next_index = (current_index + 1) % len(player_ids)
        self.game_data[group_id]['current_player'] = player_ids[next_index]

    # 辅助方法：获取游戏状态文本
    def _get_status_text(self, group_id):
        """获取游戏状态文本"""
        status = self.game_status[group_id]
        if status == 0:
            return "未开始"
        elif status == 1:
            return "等待加入"
        elif status == 2:
            if self.game_data[group_id].get('bid_stage', False):
                return "叫分阶段"
            else:
                return "出牌阶段"
        return "未知状态"

    # 辅助方法：格式化牌
    def _format_cards(self, cards):
        """格式化牌"""
        if not cards:
            return "无"
        return " ".join(cards)

    # 辅助方法：解析牌
    def _parse_cards(self, cards_str):
        """解析牌"""
        if not cards_str:
            return []
        return cards_str.split()

    # 辅助方法：检查玩家是否有这些牌
    def _has_cards(self, group_id, player_id, cards):
        """检查玩家是否有这些牌"""
        player_cards = self.player_cards[group_id][player_id].copy()
        for card in cards:
            if card in player_cards:
                player_cards.remove(card)
            else:
                return False
        return True

    # 辅助方法：移除玩家的牌
    def _remove_cards(self, group_id, player_id, cards):
        """移除玩家的牌"""
        for card in cards:
            self.player_cards[group_id][player_id].remove(card)

    # 辅助方法：获取牌的排序键
    def _card_sort_key(self, card):
        """获取牌的排序键"""
        if card == 'joker':
            return (16, 0)
        elif card == 'JOKER':
            return (17, 0)
        else:
            suit = card[0]
            rank = card[1:]
            suit_value = {'♠': 3, '♥': 2, '♦': 1, '♣': 0}.get(suit, 0)
            rank_value = self.card_values.get(rank, 0)
            return (rank_value, suit_value)

    # 辅助方法：获取牌型
    def _get_card_type(self, cards):
        """获取牌型和牌值"""
        if not cards:
            return None, None
            
        # 统计牌的数量
        card_count = {}
        for card in cards:
            if card == 'joker' or card == 'JOKER':
                rank = card
            else:
                rank = card[1:]
            card_count[rank] = card_count.get(rank, 0) + 1
            
        # 获取牌的值
        card_values = []
        for card in cards:
            if card == 'joker' or card == 'JOKER':
                rank = card
            else:
                rank = card[1:]
            card_values.append(self.card_values.get(rank, 0))
            
        # 火箭（大小王）
        if len(cards) == 2 and 'joker' in card_count and 'JOKER' in card_count:
            return self.card_types['rocket'], 0
            
        # 炸弹（四张相同点数的牌）
        if len(cards) == 4 and len(card_count) == 1:
            return self.card_types['bomb'], card_values[0]
            
        # 单牌
        if len(cards) == 1:
            return self.card_types['single'], card_values[0]
            
        # 对子
        if len(cards) == 2 and len(card_count) == 1:
            return self.card_types['pair'], card_values[0]
            
        # 三张
        if len(cards) == 3 and len(card_count) == 1:
            return self.card_types['trio'], card_values[0]
            
        # 三带一
        if len(cards) == 4 and len(card_count) == 2:
            for rank, count in card_count.items():
                if count == 3:
                    return self.card_types['trio_single'], self.card_values.get(rank, 0)
                    
        # 三带二
        if len(cards) == 5 and len(card_count) == 2:
            for rank, count in card_count.items():
                if count == 3:
                    return self.card_types['trio_pair'], self.card_values.get(rank, 0)
                    
        # 顺子（五张或更多的连续单牌）
        if len(cards) >= 5 and len(card_count) == len(cards) and max(card_values) <= 14:  # 不能超过A
            card_values.sort()
            is_straight = True
            for i in range(1, len(card_values)):
                if card_values[i] != card_values[i-1] + 1:
                    is_straight = False
                    break
            if is_straight:
                return self.card_types['straight'], card_values[0]
                
        # 连对（三对或更多的连续对子）
        if len(cards) >= 6 and len(cards) % 2 == 0 and len(card_count) == len(cards) // 2 and max(card_values) <= 14:  # 不能超过A
            # 检查是否都是对子
            is_pairs = True
            for count in card_count.values():
                if count != 2:
                    is_pairs = False
                    break
                    
            if is_pairs:
                # 检查是否连续
                unique_values = sorted(set(card_values))
                is_consecutive = True
                for i in range(1, len(unique_values)):
                    if unique_values[i] != unique_values[i-1] + 1:
                        is_consecutive = False
                        break
                if is_consecutive:
                    return self.card_types['pairs'], unique_values[0]
                    
        # 飞机（两个或更多的连续三张）
        if len(cards) >= 6 and len(cards) % 3 == 0:
            # 检查是否都是三张
            trio_ranks = []
            for rank, count in card_count.items():
                if count == 3:
                    trio_ranks.append(rank)
                    
            if len(trio_ranks) == len(cards) // 3:
                # 检查是否连续
                trio_values = [self.card_values.get(rank, 0) for rank in trio_ranks]
                trio_values.sort()
                is_consecutive = True
                for i in range(1, len(trio_values)):
                    if trio_values[i] != trio_values[i-1] + 1:
                        is_consecutive = False
                        break
                if is_consecutive:
                    return self.card_types['plane'], trio_values[0]
                    
        # 不符合任何牌型
        return None, None

    # 辅助方法：检查是否可以大过上一手牌
    def _can_beat(self, card_type, card_value, last_type, last_value):
        """检查是否可以大过上一手牌"""
        # 火箭可以大过任何牌
        if card_type == self.card_types['rocket']:
            return True
            
        # 炸弹可以大过除火箭外的任何牌
        if card_type == self.card_types['bomb']:
            if last_type == self.card_types['rocket']:
                return False
            if last_type == self.card_types['bomb']:
                return card_value > last_value
            return True
            
        # 其他牌型必须相同，且牌值更大
        if card_type == last_type:
            return card_value > last_value
            
        return False

    async def terminate(self):
        """插件销毁方法，当插件被卸载/停用时会调用。"""
        logger.info("斗地主插件已卸载")
