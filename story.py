import discord
from discord.ui import View, button

STORY_DATA = {
    "voice_1": {
        "title": "どこからか声がする",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "???", "text": "おい、聞こえるか…？"},
            {"speaker": "???", "text": "お前、まだ何も知らないのか？"},
            {"speaker": "???", "text": "とっとと戻れ。戻り方？頑張ってくれ。進んでもいい事ないぞ――。"}
        ]
    },
    "intro_2": {
        "title": "既視感",
        "loop_requirement": 1,
        "lines": [
            {"speaker": "???", "text": "お前…2回目だな？なんで進んだんだ。"},
            {"speaker": "???", "text": "死んだ時にポイント獲得したろ？あれで己を強化できる。"},
            {"speaker": "???", "text": "試しに `!upgrade` してみな。!buy_upgrade <番号> を忘れずにな。"}
        ]
    },
    "lucky_777": {
        "title": "幸運の数字",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "???", "text": "777m地点…か。"},
            {"speaker": "???", "text": "ラッキーセブン…何かいいことがあるかもな。"},
            {"speaker": "冒険者", "text": "こいつ、最初の無責任なやつにどこか似ているような、気のせいか"}
        ]
    },
    "story_250": {
        "title": "最初の痕跡",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "冒険者", "text": "壁に刻まれた文字を発見した。"},
            {"speaker": "古代文字", "text": "「ここは始まりに過ぎない。真実は深淵の底に眠る」"},
            {"speaker": "ナレーション", "text": "誰がいつ、なぜこれを刻んだのだろうか…"}
        ]
    },
    "story_750": {
        "title": "骸骨の山",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "おびただしい数の骸骨が積み上げられている。"},
            {"speaker": "ナレーション", "text": "これは…冒険者たちの成れの果てか？"},
            {"speaker": "ナレーション", "text": "恐怖が背筋を走るが、進むしかない。"}
        ]
    },
    "story_1250": {
        "title": "謎の老人",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "老人", "text": "よう、若造。まだ生きてるのか。"},
            {"speaker": "老人", "text": "この先、さらに地獄が待ってるぜ。"},
            {"speaker": "老人", "text": "だが、お前には…何か特別なものを感じるな。頑張れよ。"},
            {"speaker": "ナレーション", "text": "老人はそう言うと、闇の中へ消えていった…"}
        ]
    },
    "story_1750": {
        "title": "幻影の声",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "???", "text": "…助けて…"},
            {"speaker": "ナレーション", "text": "どこからか助けを求める声が聞こえる。"},
            {"speaker": "ナレーション", "text": "しかし、周囲には誰もいない。"},
            {"speaker": "ナレーション", "text": "このダンジョンには、何かがいる…"}
        ]
    },
    "story_2250": {
        "title": "古の記録",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "古びた日記を見つけた。"},
            {"speaker": "日記", "text": "「100日目。もう戻れないことは分かっている」"},
            {"speaker": "日記", "text": "「だが、私は真実に辿り着かねばならない」"},
            {"speaker": "ナレーション", "text": "この冒険者は、どうなったのだろう…"}
        ]
    },
    "story_2750": {
        "title": "鏡の間",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "鏡張りの部屋に出た。"},
            {"speaker": "ナレーション", "text": "鏡に映る自分を見る…傷だらけだ。"},
            {"speaker": "鏡の中の自分", "text": "「お前は…本当にここまで来るべきだったのか？」"},
            {"speaker": "ナレーション", "text": "鏡の中の自分が語りかけてきた。幻覚か？"}
        ]
    },
    "story_3250": {
        "title": "封印の扉",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "巨大な扉を発見した。"},
            {"speaker": "扉の碑文", "text": "「この先に進む者は、覚悟を持て」"},
            {"speaker": "扉の碑文", "text": "「引き返すことはもはや許されぬ」"},
            {"speaker": "ナレーション", "text": "だが、扉は既に開いている…先人がいたのか？"}
        ]
    },
    "story_3750": {
        "title": "魂の囁き",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "亡霊", "text": "ここまで…来たか…"},
            {"speaker": "亡霊", "text": "私は…かつてこのダンジョンに挑んだお前だ…"},
            {"speaker": "亡霊", "text": "お前も……同じ運命を辿るのだろう…"},
            {"speaker": "ナレーション", "text": "亡霊は光となって消えていった。\n\nあいつはなんだったんだ？"}
        ]
    },
    "story_4250": {
        "title": "深淵への階段",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "遥か下へと続く螺旋階段を見つけた。"},
            {"speaker": "ナレーション", "text": "底が見えないほど深い…"},
            {"speaker": "ナレーション", "text": "ここから先は、真の試練が待っているのだろう。"}
        ]
    },
    "story_4750": {
        "title": "魔力の泉",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "神秘的な泉を発見した。"},
            {"speaker": "ナレーション", "text": "水面が青白く光っている。"},
            {"speaker": "ナレーション", "text": "水を飲むと、不思議な力が体を巡った…気がする。多分気のせい――。"}
        ]
    },
    "story_5250": {
        "title": "崩壊の予兆",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "ダンジョンが微かに揺れている。"},
            {"speaker": "ナレーション", "text": "天井から小石が落ちてきた。"},
            {"speaker": "???", "text": "「このダンジョンは……普通に脆いだけだ。」"},
            {"speaker": "ナレーション", "text": "こいつはなんなんだ…"}
        ]
    },
    "story_5750": {
        "title": "真実の一端",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "謎の碑文", "text": "「このダンジョンは昔の先人が作りし物――」"},
            {"speaker": "謎の碑文", "text": "「最深部には、このダンジョンの全貌が隠されている……\nby : 製作者」"},
            {"speaker": "ナレーション", "text": "それが本当なら、進むしかないな。"}
        ]
    },
    "story_6250": {
        "title": "絶望の記録",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "血で書かれたメッセージがある。"},
            {"speaker": "メッセージ", "text": "「この記録を見た者よ…」"},
            {"speaker": "メッセージ", "text": "「何回同じところを歩くんだ……？」"},
            {"speaker": "ナレーション", "text": "書いた者は、もういない――"}
        ]
    },
    "story_6750": {
        "title": "決意の刻",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "ここまで来た。"},
            {"speaker": "ナレーション", "text": "もう戻ることはできない。"},
            {"speaker": "ナレーション", "text": "最深部は近い。"},
            {"speaker": "ナレーション", "text": "全ての答えが、そこにある。"}
        ]
    },
    "story_7250": {
        "title": "光と闇の境界",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "突然、眩しい光が差し込んできた。"},
            {"speaker": "ナレーション", "text": "だが、その先にはさらに深い闇が広がっている。"},
            {"speaker": "???", "text": "「ああっ………目がっ…！目がぁぁぁぁあっ！！」"},
            {"speaker": "ナレーション", "text": "真実に近づいている…？あれは'バ〇ス'だったのか……"}
        ]
    },
    "story_7750": {
        "title": "過去の幻影",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "幻が見える…かつての戦いの記憶だ。"},
            {"speaker": "幻影の戦士", "text": "「私たちは…???を倒すために…」"},
            {"speaker": "幻影の戦士", "text": "「だが…力及ばず…」"},
            {"speaker": "ナレーション", "text": "幻影は消えた。倒そうとした相手は誰だったのだろう？"}
        ]
    },
    "story_8250": {
        "title": "岩盤の崩壊",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "岩盤に大きな穴が空いている"},
            {"speaker": "ナレーション", "text": "これは…誰かが叩きつけられたものか？"},
            {"speaker": "???", "text": "「お、お前と一緒にぃ……ひ、避難する準備だぁ！」"},
            {"speaker": "ナレーション", "text": "1人用の'それ'でかぁ？\n\nバカバカしい。先に進もう。"}
        ]
    },
    "story_8750": {
        "title": "最終決戦前夜",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "空気が重い…"},
            {"speaker": "ナレーション", "text": "何者かの気配を強く感じる。"},
            {"speaker": "ナレーション", "text": "覚悟を決める時が来た。"},
            {"speaker": "ナレーション", "text": "この先に、全てが待っている。"}
        ]
    },
    "story_9250": {
        "title": "???の間近",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "???", "text": "「ここまで来ちまったのか？」"},
            {"speaker": "???", "text": "「お前には倒せない。戦いたくないから帰ってくれ」"},
            {"speaker": "ナレーション", "text": "声が…直接頭に響いてくる。"},
            {"speaker": "ナレーション", "text": "もう後戻りはできない！"}
        ]
    },
    "story_9750": {
        "title": "最後の一歩",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "目の前から不穏な雰囲気が漂う"},
            {"speaker": "ナレーション", "text": "ここまでの全ての戦いが、この瞬間のためにあった。"},
            {"speaker": "ナレーション", "text": "深呼吸をする…"},
            {"speaker": "ナレーション", "text": "考えてても始まらない！"}
        ]
    },
    "boss_pre_1": {
        "title": "第一の試練",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "ダンジョンの奥から、強大な気配が感じられる。"},
            {"speaker": "ナレーション", "text": "これが…最初の番人か。"},
            {"speaker": "スライムキング", "text": "「スライムだからって、いじめるのはやめてほしいです！」"},
            {"speaker": "ナレーション", "text": "戦いの時が来た！"}
        ]
    },
    "boss_post_1": {
        "title": "最初の勝利",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "番人を倒した…！"},
            {"speaker": "ナレーション", "text": "これで先に進める。"},
            {"speaker": "ナレーション", "text": "スライムさん、すみません。"}
        ]
    },
    "boss_pre_2": {
        "title": "暗闇の守護者",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "深淵がさらに深まっていく…"},
            {"speaker": "謎の声", "text": "貴様ごときが、この『道』を越えられるとでも思ったか？\n\n失礼なやつだな"},
            {"speaker": "ナレーション", "text": "闇の中から、巨大な影が姿を現す！"}
        ]
    },
    "boss_post_2": {
        "title": "闇を超えて",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "デスロードを退けた。"},
            {"speaker": "ナレーション", "text": "『あんなこと言ってイキってた癖にめっちゃ弱かったな。』"},
            {"speaker": "ナレーション", "text": "次なる試練へと歩こう"}
        ]
    },
    "boss_pre_3": {
        "title": "炎の支配者",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "辺りが急激に熱くなる…"},
            {"speaker": "炎の声", "text": "「我が炎で、お前を灰にしてやろう！」"},
            {"speaker": "ナレーション", "text": "炎を纏った巨獣が立ちはだかる！"}
        ]
    },
    "boss_post_3": {
        "title": "炎を制す",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "炎の支配者を倒した！"},
            {"speaker": "ナレーション", "text": "せっかくなら残り火で焼き芋でも作ろう"},
            {"speaker": "ナレーション", "text": "まだ旅は続く。"}
        ]
    },
    "boss_pre_4": {
        "title": "見えない",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "突然、当たりが暗くなる"},
            {"speaker": "ボスらしき声", "text": "『さあ、我がおぞましき姿に恐れるがいい！』"},
            {"speaker": "ナレーション", "text": "暗くて姿が見えない。"}
        ]
    },
    "boss_post_4": {
        "title": "闇を打ち破って",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "闇の王を打ち破った！"},
            {"speaker": "ナレーション", "text": "辺りが明るくなる…"},
            {"speaker": "ナレーション", "text": "冒険は続く。"}
        ]
    },
    "boss_pre_5": {
        "title": "雷鳴の王",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "空間が震え、雷鳴が轟く。"},
            {"speaker": "雷の声", "text": "「我が雷撃で消し去ってやる！」"},
            {"speaker": "ナレーション", "text": "雷を操る王が姿を現す！"}
        ]
    },
    "boss_post_5": {
        "title": "雷を超えて",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "雷鳴の王を倒した！"},
            {"speaker": "ナレーション", "text": "久しぶりの電気だ。\n『何かに使えないかな？』"},
            {"speaker": "ナレーション", "text": "半分まで来た。まだまだ続く。"}
        ]
    },
    "boss_pre_6": {
        "title": "おねえさん",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "鼻が人参の雪だるまがいる"},
            {"speaker": "???", "text": "『倒してかき氷にしちゃえよ』\n天才か？"},
            {"speaker": "ナレーション", "text": "初めてこの声に感謝した気がする。"}
        ]
    },
    "boss_post_6": {
        "title": "極寒を超えて",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "氷の女王を倒した！"},
            {"speaker": "ナレーション", "text": "これでかき氷！"},
            {"speaker": "ナレーション", "text": "振り返ると、氷は溶けていた――。"}
        ]
    },
    "boss_pre_7": {
        "title": "獄炎の巨人",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "巨大な存在が目を覚ます…"},
            {"speaker": "ナレーション", "text": "巨人が立ち上がる！"}
        ]
    },
    "boss_post_7": {
        "title": "巨人殺し",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "巨人を討ち取った"},
            {"speaker": "ナレーション", "text": "『ガタイが良すぎて動けてなかったな。』"},
            {"speaker": "ナレーション", "text": "もう7割以上進んだ。気を引き締めよう"}
        ]
    },
    "boss_pre_8": {
        "title": "死神の到来",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "死の気配が濃厚になる…"},
            {"speaker": "死神", "text": "「お前の魂、いただくぞ…」"},
            {"speaker": "ナレーション", "text": "深淵の守護神が鎌を振りかざす！"}
        ]
    },
    "boss_post_8": {
        "title": "死を超えて",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "なんとか退けた！"},
            {"speaker": "ナレーション", "text": "『この魂は誰のものなんだろう』"},
            {"speaker": "ナレーション", "text": "ゴールもう目前だ。"}
        ]
    },
    "boss_pre_9": {
        "title": "カオスからの挑戦",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "龍", "text": "混沌こそ想像の源！！！"},
            {"speaker": "ナレーション", "text": "……こいつ大丈夫か？"},
            {"speaker": "龍", "text": "「あいつの前に、お前を倒す！」"},
            {"speaker": "ナレーション", "text": "やばそうな龍との戦いが始まる！"}
        ]
    },
    "boss_post_9": {
        "title": "最後の番人を越えて",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "カオスを倒した…！"},
            {"speaker": "ナレーション", "text": "龍は闇に消えた。"},
            {"speaker": "ナレーション", "text": "次は…ボスだ。"}
        ]
    },
    "boss_pre_10": {
        "title": "???との決戦",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "ついに…到達した。"},
            {"speaker": "???", "text": "『帰れって言ったろ？なんで来た』"},
            {"speaker": "???", "text": "『来たなら戦わねえと行けないから嫌なんだ……』"},
            {"speaker": "ナレーション", "text": "運命の戦いが、今始まる！"}
        ]
    },
    "boss_post_10": {
        "title": "救済……？",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "???を倒した"},
            {"speaker": "???", "text": "「…まさか…俺に…」"},
            {"speaker": "ナレーション", "text": "???は光となって消えていった。"},
            {"speaker": "ナレーション", "text": "あいつは何者だったんだ？"},
            {"speaker": "ナレーション", "text": "おめでとう、冒険者よ。"}
        ]
    },
    "story_250_loop2": {
        "title": "既視感の文字",
        "loop_requirement": 2,
        "lines": [
            {"speaker": "ナレーション", "text": "壁の文字を見つけた…これは前にも見た。"},
            {"speaker": "古代文字", "text": "「ここは始まりに過ぎない。真実は深淵の底に眠る」"},
            {"speaker": "あなた", "text": "（やはり同じ文字だ…これは繰り返しなのか？）"}
        ]
    },
    "story_750_loop2": {
        "title": "変わらぬ骸骨",
        "loop_requirement": 2,
        "lines": [
            {"speaker": "ナレーション", "text": "また、あの骸骨の山だ…"},
            {"speaker": "あなた", "text": "（前回もここで見た。少し増えているような…）"},
            {"speaker": "ナレーション", "text": "不気味な既視感が襲ってくる。"}
        ]
    },
    "story_1250_loop2": {
        "title": "老人の忠告",
        "loop_requirement": 2,
        "lines": [
            {"speaker": "老人", "text": "また会ったな…お前、気づいているか？"},
            {"speaker": "老人", "text": "この世界は…何度も繰り返されている。"},
            {"speaker": "老人", "text": "だが、お前は強くなっている。それが希望だ。"},
            {"speaker": "ナレーション", "text": "老人の言葉が心に残る…"}
        ]
    },
    "story_250_loop3": {
        "title": "真実に近づく",
        "loop_requirement": 3,
        "lines": [
            {"speaker": "ナレーション", "text": "また同じ文字…だが、今回は何かが違う。"},
            {"speaker": "古代文字", "text": "「繰り返す者よ、真実はお前の中にある」"},
            {"speaker": "あなた", "text": "（文字が…変わった？なぜ？）"}
        ]
    },
    "story_750_loop3": {
        "title": "骸骨の真実",
        "loop_requirement": 3,
        "lines": [
            {"speaker": "ナレーション", "text": "骸骨の山…だが、今回はよく見える。"},
            {"speaker": "ナレーション", "text": "これは…全て同じ人物の骨だ。"},
            {"speaker": "あなた", "text": "（まさか…これは全て、私…？）"},
            {"speaker": "ナレーション", "text": "恐ろしい妄想が浮かび上がる。"}
        ]
    },
    "story_1250_loop3": {
        "title": "老人の正体",
        "loop_requirement": 3,
        "lines": [
            {"speaker": "老人", "text": "3回目…か。よくここまで来た。"},
            {"speaker": "老人", "text": "実はな…私もお前だ。遥か未来のな。"},
            {"speaker": "あなた", "text": "（何を言っている…？）"},
            {"speaker": "老人", "text": "いつか分かる。その時まで、諦めるな。"},
            {"speaker": "ナレーション", "text": "老人は煙のように消えていった…"}
        ]
    },
    
    # ==============================
    # 選択肢付きストーリー（サンプル）
    # ==============================
    "choice_mysterious_door": {
        "title": "謎の扉",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "目の前に2つの扉が現れた。"},
            {"speaker": "ナレーション", "text": "左の扉からは光が漏れている。右の扉からは闇が滲み出ている。"}
        ],
        "choices": [
            {
                "label": "① 光の扉を開ける",
                "result": {
                    "title": "光の選択",
                    "lines": [
                        {"speaker": "ナレーション", "text": "光の扉を開けた。"},
                        {"speaker": "ナレーション", "text": "温かい光に包まれ、HPが回復した！"}
                    ],
                    "reward": "hp_restore"
                }
            },
            {
                "label": "② 闇の扉を開ける", 
                "result": {
                    "title": "闇の選択",
                    "lines": [
                        {"speaker": "ナレーション", "text": "闇の扉を開けた。"},
                        {"speaker": "ナレーション", "text": "闇から強力な武器が現れた！"}
                    ],
                    "reward": "weapon_drop"
                }
            }
        ]
    },
    "choice_strange_merchant": {
        "title": "怪しい商人",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "商人", "text": "ようこそ、旅人よ…"},
            {"speaker": "商人", "text": "特別な取引をしよう。金貨100枚で、何かをあげよう。"},
            {"speaker": "商人", "text": "さあ、どちらを選ぶ？"}
        ],
        "choices": [
            {
                "label": "① 取引を受ける（-100G）",
                "result": {
                    "title": "取引成立",
                    "lines": [
                        {"speaker": "商人", "text": "賢い選択だ…これを受け取りたまえ。"},
                        {"speaker": "ナレーション", "text": "謎のアイテムを手に入れた！"}
                    ],
                    "reward": "item_drop",
                    "gold_cost": 100
                }
            },
            {
                "label": "② 断る",
                "result": {
                    "title": "賢明な判断",
                    "lines": [
                        {"speaker": "商人", "text": "ふむ…慎重だな。"},
                        {"speaker": "ナレーション", "text": "商人は闇に消えていった…"}
                    ],
                    "reward": "none"
                }
            }
        ]
    },
    "choice_fork_road": {
        "title": "分かれ道",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "道が二手に分かれている。"},
            {"speaker": "ナレーション", "text": "左の道は平坦で歩きやすそうだ。右の道は険しく危険そうだ。"}
        ],
        "choices": [
            {
                "label": "① 左の安全な道を進む",
                "result": {
                    "title": "安全第一",
                    "lines": [
                        {"speaker": "ナレーション", "text": "安全な道を選んだ。"},
                        {"speaker": "ナレーション", "text": "無事に進むことができた。"}
                    ],
                    "reward": "small_gold"
                }
            },
            {
                "label": "② 右の険しい道に挑む",
                "result": {
                    "title": "危険な賭け",
                    "lines": [
                        {"speaker": "ナレーション", "text": "険しい道を選んだ…"},
                        {"speaker": "ナレーション", "text": "道中で傷を負ったが、貴重な宝を発見した！"}
                    ],
                    "reward": "rare_item_with_damage"
                }
            }
        ]
    },
    "choice_mysterious_well": {
        "title": "神秘の井戸",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "古い井戸を見つけた。"},
            {"speaker": "???", "text": "「硬貨を投げ入れると、願いが叶うかもしれない…」"}
        ],
        "choices": [
            {
                "label": "① 金貨を投げ入れる（-50G）",
                "result": {
                    "title": "願いの代償",
                    "lines": [
                        {"speaker": "ナレーション", "text": "金貨を井戸に投げ入れた。"},
                        {"speaker": "ナレーション", "text": "井戸が光り輝き、力が湧いてきた！"}
                    ],
                    "reward": "max_hp_boost",
                    "gold_cost": 50
                }
            },
            {
                "label": "② 何もせず立ち去る",
                "result": {
                    "title": "現実的な判断",
                    "lines": [
                        {"speaker": "ナレーション", "text": "怪しい井戸には近づかないことにした。"},
                        {"speaker": "ナレーション", "text": "無難な選択だ…"}
                    ],
                    "reward": "none"
                }
            }
        ]
    },
    "choice_sleeping_dragon": {
        "title": "眠る竜",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "巨大な竜が眠っている…"},
            {"speaker": "ナレーション", "text": "その傍らには、光り輝く宝珠がある。"}
        ],
        "choices": [
            {
                "label": "① 宝珠を盗む",
                "result": {
                    "title": "危険な強奪",
                    "lines": [
                        {"speaker": "ナレーション", "text": "そっと宝珠を掴んだ…"},
                        {"speaker": "ナレーション", "text": "竜が目を覚ます前に逃げ出した！"}
                    ],
                    "reward": "legendary_item"
                }
            },
            {
                "label": "② 見逃して進む",
                "result": {
                    "title": "慎重な選択",
                    "lines": [
                        {"speaker": "ナレーション", "text": "竜を起こすのは危険だ…"},
                        {"speaker": "ナレーション", "text": "静かにその場を後にした。"}
                    ],
                    "reward": "none"
                }
            }
        ]
    },
    "choice_cursed_treasure": {
        "title": "呪われた財宝",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "ナレーション", "text": "黄金の山を発見した！"},
            {"speaker": "???", "text": "「これは呪われている…触れれば代償を払うことになるぞ」"}
        ],
        "choices": [
            {
                "label": "① 黄金を奪う",
                "result": {
                    "title": "欲望の代償",
                    "lines": [
                        {"speaker": "ナレーション", "text": "黄金を掴んだ瞬間、激しい痛みが走る！"},
                        {"speaker": "ナレーション", "text": "それでも大金を手に入れた…"}
                    ],
                    "reward": "gold_with_damage"
                }
            },
            {
                "label": "② 誘惑に負けず去る",
                "result": {
                    "title": "克己の心",
                    "lines": [
                        {"speaker": "ナレーション", "text": "欲望を抑え、黄金を諦めた。"},
                        {"speaker": "ナレーション", "text": "心が軽くなった気がする…"}
                    ],
                    "reward": "mp_restore"
                }
            }
        ]
    },
    "choice_time_traveler": {
        "title": "時の旅人",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "旅人", "text": "君は…選ばれし者だな。"},
            {"speaker": "旅人", "text": "私は時を超える者。君に過去か未来、どちらかを見せてあげよう。"}
        ],
        "choices": [
            {
                "label": "① 過去を見る",
                "result": {
                    "title": "忘れられた記憶",
                    "lines": [
                        {"speaker": "ナレーション", "text": "過去のビジョンが見えた…"},
                        {"speaker": "ナレーション", "text": "かつての勇者たちの戦いが蘇る。経験値を得た！"}
                    ],
                    "reward": "exp_boost"
                }
            },
            {
                "label": "② 未来を見る",
                "result": {
                    "title": "運命の予兆",
                    "lines": [
                        {"speaker": "ナレーション", "text": "未来のビジョンが見えた…"},
                        {"speaker": "ナレーション", "text": "恐ろしい敵が待ち受けている…しかし、対策が分かった！"}
                    ],
                    "reward": "defense_boost"
                }
            }
        ]
    },
    "choice_fairy_spring": {
        "title": "妖精の泉",
        "loop_requirement": 0,
        "lines": [
            {"speaker": "妖精", "text": "こんにちは、冒険者さん♪"},
            {"speaker": "妖精", "text": "この泉には不思議な力があるの。選んで？"}
        ],
        "choices": [
            {
                "label": "① 力の泉に入る",
                "result": {
                    "title": "力の祝福",
                    "lines": [
                        {"speaker": "妖精", "text": "力の泉を選んだのね！"},
                        {"speaker": "ナレーション", "text": "体中に力が満ちてくる！攻撃力が上昇した！"}
                    ],
                    "reward": "attack_boost"
                }
            },
            {
                "label": "② 癒しの泉に入る",
                "result": {
                    "title": "癒しの祝福",
                    "lines": [
                        {"speaker": "妖精", "text": "癒しの泉を選んだのね！"},
                        {"speaker": "ナレーション", "text": "温かな光に包まれ、傷が癒えていく…"}
                    ],
                    "reward": "full_heal"
                }
            }
        ]
    },
}


class StoryView(View):
    def __init__(self, user_id: int, story_id: str, user_processing: dict, callback_data: dict = None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.story_id = story_id
        self.user_processing = user_processing
        self.current_page = 0
        self.callback_data = callback_data
        self.ctx = None
        
        story = STORY_DATA.get(story_id)
        if not story:
            self.story_title = "不明なストーリー"
            self.story_lines = [{"speaker": "システム", "text": "ストーリーが見つかりません。"}]
            self.choices = None
        else:
            self.story_title = story["title"]
            self.story_lines = story["lines"]
            self.choices = story.get("choices")  # 選択肢があれば取得
    
    def get_embed(self):
        if self.current_page >= len(self.story_lines):
            self.current_page = len(self.story_lines) - 1
        
        line = self.story_lines[self.current_page]
        speaker = line.get("speaker", "???")
        text = line.get("text", "")
        
        embed = discord.Embed(
            title=f"📖 {self.story_title}",
            description=f"**{speaker}**：{text}",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"ページ {self.current_page + 1}/{len(self.story_lines)}")
        
        return embed
    
    async def send_story(self, ctx_or_interaction):
        # ctxを保存（選択肢処理で使用）
        if hasattr(ctx_or_interaction, 'channel'):
            self.ctx = ctx_or_interaction
        
        embed = self.get_embed()
        
        if hasattr(ctx_or_interaction, 'channel'):
            self.message = await ctx_or_interaction.channel.send(embed=embed, view=self)
        else:
            await ctx_or_interaction.response.edit_message(embed=embed, view=self)
            self.message = await ctx_or_interaction.original_response()
    
    @button(label="◀ BACK", style=discord.ButtonStyle.secondary)
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのストーリーではありません！", ephemeral=True)
            return
        
        if self.current_page > 0:
            self.current_page -= 1
        
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)
    
    @button(label="NEXT ▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("これはあなたのストーリーではありません！", ephemeral=True)
            return
        
        if self.current_page < len(self.story_lines) - 1:
            self.current_page += 1
            embed = self.get_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            import db
            
            # 選択肢がある場合は選択Viewを表示
            if self.choices:
                choice_view = StoryChoiceView(self.user_id, self.story_id, self.choices, self.user_processing, self.ctx)
                embed = discord.Embed(
                    title=f"🔮 {self.story_title}",
                    description="どちらを選びますか？",
                    color=discord.Color.gold()
                )
                await interaction.response.edit_message(embed=embed, view=choice_view)
                return
            
            # 選択肢がない場合は通常通り完了
            db.set_story_flag(self.user_id, self.story_id)
            
            embed = discord.Embed(
                title="📘 ストーリー完了！",
                description="物語が一区切りついた。冒険を続けよう。",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed, view=None)
            
            if self.callback_data and self.callback_data.get('type') == 'boss_battle':
                import asyncio
                await asyncio.sleep(1.5)
                
                import game
                from views import BossBattleView, FinalBossBattleView
                
                boss_stage = self.callback_data['boss_stage']
                ctx = self.callback_data['ctx']
                
                boss = game.get_boss(boss_stage)
                if boss:
                    player = db.get_player(self.user_id)
                    player_data = {
                        "hp": player.get("hp", 100),
                        "attack": player.get("atk", 10),
                        "defense": player.get("def", 5),
                        "inventory": player.get("inventory", []),
                        "distance": player.get("distance", 0),
                        "user_id": self.user_id
                    }
                    
                    if boss_stage == 10:
                        embed = discord.Embed(
                            title="⚔️ ラスボス出現！",
                            description=f"**{boss['name']}** が最後の戦いに臨む！\n\nこれが最終決戦だ…！",
                            color=discord.Color.dark_gold()
                        )
                        await ctx.channel.send(embed=embed)
                        await asyncio.sleep(2)
                        
                        view = FinalBossBattleView(ctx, player_data, boss, self.user_processing, boss_stage)
                        await view.send_initial_embed()
                    else:
                        embed = discord.Embed(
                            title="⚠️ ボス出現！",
                            description=f"**{boss['name']}** が立ちはだかる！",
                            color=discord.Color.dark_red()
                        )
                        await ctx.channel.send(embed=embed)
                        await asyncio.sleep(1.5)
                        
                        view = BossBattleView(ctx, player_data, boss, self.user_processing, boss_stage)
                        await view.send_initial_embed()
            else:
                if self.user_id in self.user_processing:
                    self.user_processing[self.user_id] = False


class StoryChoiceView(View):
    """ストーリー選択肢View"""
    def __init__(self, user_id: int, story_id: str, choices: list, user_processing: dict, ctx):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.story_id = story_id
        self.choices = choices
        self.user_processing = user_processing
        self.ctx = ctx
        
        for idx, choice in enumerate(choices):
            btn = discord.ui.Button(
                label=choice["label"],
                style=discord.ButtonStyle.primary if idx == 0 else discord.ButtonStyle.secondary,
                custom_id=f"choice_{idx}"
            )
            btn.callback = self.create_choice_callback(idx)
            self.add_item(btn)
    
    def create_choice_callback(self, choice_idx):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("これはあなたの選択ではありません！", ephemeral=True)
                return
            
            import db
            import game
            import random
            
            choice = self.choices[choice_idx]
            result = choice["result"]
            
            lines_text = "\n".join([f"**{line['speaker']}**：{line['text']}" for line in result["lines"]])
            
            embed = discord.Embed(
                title=f"✨ {result['title']}",
                description=lines_text,
                color=discord.Color.gold()
            )
            
            reward_text = ""
            player = db.get_player(self.user_id)
            
            if result.get("reward") == "hp_restore":
                max_hp = player.get("max_hp", 100)
                heal_amount = int(max_hp * 0.5)
                new_hp = min(max_hp, player.get("hp", 100) + heal_amount)
                db.update_player(self.user_id, hp=new_hp)
                reward_text = f"\n\n💚 HP +{heal_amount} 回復！"
            
            elif result.get("reward") == "weapon_drop":
                weapons = [w for w, info in game.ITEMS_DATABASE.items() if info.get('type') == 'weapon']
                if weapons:
                    weapon = random.choice(weapons)
                    db.add_item_to_inventory(self.user_id, weapon)
                    reward_text = f"\n\n⚔️ **{weapon}** を手に入れた！"
            
            elif result.get("reward") == "item_drop":
                gold_cost = result.get("gold_cost", 0)
                current_gold = player.get("gold", 0)
                
                if current_gold >= gold_cost:
                    items = list(game.ITEMS_DATABASE.keys())
                    item = random.choice(items)
                    db.add_item_to_inventory(self.user_id, item)
                    db.add_gold(self.user_id, -gold_cost)
                    reward_text = f"\n\n💰 -{gold_cost}G\n📦 **{item}** を手に入れた！"
                else:
                    reward_text = f"\n\n💸 ゴールドが足りない…（必要: {gold_cost}G）"
            
            elif result.get("reward") == "small_gold":
                gold_amount = random.randint(30, 80)
                db.add_gold(self.user_id, gold_amount)
                reward_text = f"\n\n💰 {gold_amount}G を手に入れた！"
            
            elif result.get("reward") == "rare_item_with_damage":
                rare_items = [w for w, info in game.ITEMS_DATABASE.items() if info.get('attack', 0) >= 20 or info.get('defense', 0) >= 15]
                if rare_items:
                    item = random.choice(rare_items)
                    db.add_item_to_inventory(self.user_id, item)
                    damage = random.randint(15, 30)
                    new_hp = max(1, player.get("hp", 100) - damage)
                    db.update_player(self.user_id, hp=new_hp)
                    reward_text = f"\n\n📦 **{item}** を手に入れた！\n💔 HP -{damage}"
            
            elif result.get("reward") == "max_hp_boost":
                gold_cost = result.get("gold_cost", 0)
                current_gold = player.get("gold", 0)
                
                if current_gold >= gold_cost:
                    current_max_hp = player.get("max_hp", 100)
                    new_max_hp = current_max_hp + 20
                    db.update_player(self.user_id, max_hp=new_max_hp)
                    db.add_gold(self.user_id, -gold_cost)
                    reward_text = f"\n\n💰 -{gold_cost}G\n❤️ 最大HP +20！（{current_max_hp} → {new_max_hp}）"
                else:
                    reward_text = f"\n\n💸 ゴールドが足りない…（必要: {gold_cost}G）"
            
            elif result.get("reward") == "legendary_item":
                legendary_items = [w for w, info in game.ITEMS_DATABASE.items() if info.get('attack', 0) >= 30 or info.get('defense', 0) >= 25]
                if legendary_items:
                    item = random.choice(legendary_items)
                    db.add_item_to_inventory(self.user_id, item)
                    reward_text = f"\n\n✨ 伝説の **{item}** を手に入れた！"
            
            elif result.get("reward") == "gold_with_damage":
                gold_amount = random.randint(200, 400)
                db.add_gold(self.user_id, gold_amount)
                damage = random.randint(20, 40)
                new_hp = max(1, player.get("hp", 100) - damage)
                db.update_player(self.user_id, hp=new_hp)
                reward_text = f"\n\n💰 {gold_amount}G を手に入れた！\n💔 HP -{damage}"
            
            elif result.get("reward") == "mp_restore":
                max_mp = player.get("max_mp", 100)
                heal_amount = int(max_mp * 0.5)
                new_mp = min(max_mp, player.get("mp", 100) + heal_amount)
                db.update_player(self.user_id, mp=new_mp)
                reward_text = f"\n\n💙 MP +{heal_amount} 回復！"
            
            elif result.get("reward") == "exp_boost":
                atk_boost = random.randint(3, 8)
                current_atk = player.get("atk", 10)
                db.update_player(self.user_id, atk=current_atk + atk_boost)
                reward_text = f"\n\n⚔️ 攻撃力 +{atk_boost}！（{current_atk} → {current_atk + atk_boost}）"
            
            elif result.get("reward") == "defense_boost":
                def_boost = random.randint(3, 8)
                current_def = player.get("def", 5)
                db.update_player(self.user_id, def_=current_def + def_boost)
                reward_text = f"\n\n🛡️ 防御力 +{def_boost}！（{current_def} → {current_def + def_boost}）"
            
            elif result.get("reward") == "attack_boost":
                atk_boost = random.randint(5, 10)
                current_atk = player.get("atk", 10)
                db.update_player(self.user_id, atk=current_atk + atk_boost)
                reward_text = f"\n\n⚔️ 攻撃力 +{atk_boost}！（{current_atk} → {current_atk + atk_boost}）"
            
            elif result.get("reward") == "full_heal":
                max_hp = player.get("max_hp", 100)
                max_mp = player.get("max_mp", 100)
                db.update_player(self.user_id, hp=max_hp, mp=max_mp)
                reward_text = f"\n\n✨ HP・MP完全回復！"
            
            embed.description += reward_text
            
            await interaction.response.edit_message(embed=embed, view=None)
            
            db.set_story_flag(self.user_id, self.story_id)
            
            if self.user_id in self.user_processing:
                self.user_processing[self.user_id] = False
        
        return callback
