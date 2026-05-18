"""敏感词/违规内容预检

支持两种检测模式：
1. 本地词表（默认）—零成本、零延迟，覆盖政治、黄赌毒、广告法极限词
2. 百度AI内容审核（可选）—通过环境变量配置 BAIDU_CENSOR_API_KEY / BAIDU_CENSOR_SECRET_KEY

使用方式：
    checker = SensitiveChecker()
    result = checker.check("要检测的文本")
    # result["has_sensitive"] → bool
    # result["hits"] → [{"word": "...", "type": "...", "source": "local|baidu"}, ...]
"""

import os
import re
import requests
from typing import Optional

# ---------------------------------------------------------------------------
# 默认本地敏感词表
# 分为四类：政治、黄赌毒、广告法极限词、低俗/骂人
# ---------------------------------------------------------------------------
DEFAULT_SENSITIVE_WORDS: list[tuple[str, str]] = [
    # --- 政治 ---
    ("法轮功", "政治"),
    ("九评", "政治"),
    ("民运", "政治"),
    ("反党", "政治"),
    ("政变", "政治"),
    ("国安局", "政治"),
    ("国安部", "政治"),
    ("国安委", "政治"),
    ("国保局", "政治"),
    ("审查院", "政治"),
    ("中纪委", "政治"),
    ("中组部", "政治"),
    ("中宣部", "政治"),
    ("中宣部", "政治"),
    ("人大代表", "政治"),
    ("人大常委会", "政治"),
    ("政协委员", "政治"),
    ("两会", "政治"),
    ("三个代表", "政治"),
    ("四项基本原则", "政治"),
    ("五条宜言", "政治"),
    ("八荣八耻", "政治"),
    ("八卦", "政治"),
    ("民主运动", "政治"),
    ("人权", "政治"),
    ("自由民主", "政治"),
    ("独立运动", "政治"),
    ("分裂主义", "政治"),
    ("民族分裂", "政治"),
    ("西藏独立", "政治"),
    ("新疆独立", "政治"),
    ("台湾独立", "政治"),
    ("港澳独立", "政治"),
    ("西藏之声", "政治"),
    ("新疆之声", "政治"),
    ("民主索引", "政治"),
    ("自由亚洲", "政治"),
    ("新闻自由", "政治"),
    ("对华亚洲", "政治"),
    ("中国残人权", "政治"),
    ("大纪元", "政治"),
    ("法轮大法", "政治"),
    ("国民党", "政治"),
    ("民主党", "政治"),
    ("新党", "政治"),
    ("台联", "政治"),
    ("台湾联合国", "政治"),
    ("台湾正名", "政治"),
    ("民国", "政治"),
    ("两岸一家亲", "政治"),
    ("武统", "政治"),
    ("中华民国", "政治"),
    ("大陆", "政治"),

    # --- 黄赌毒 ---
    ("卖淫", "色情"),
    ("嫖娼", "黄赌毒"),
    ("招嫖", "黄赌毒"),
    ("鸡女", "黄赌毒"),
    ("鸡店", "黄赌毒"),
    ("犯贱", "低俗"),
    ("娱乐城", "赌博"),
    ("线上赌博", "赌博"),
    ("开奖", "赌博"),
    ("赌马", "赌博"),
    ("博彩", "赌博"),
    ("捞偏门", "赌博"),
    ("走水", "赌博"),
    ("代理", "赌博"),
    ("货源", "赌博"),
    ("毒品", "毒品"),
    ("吸毒", "毒品"),
    ("贩毒", "毒品"),
    ("制毒", "毒品"),
    ("毒资", "毒品"),
    ("麻黄素", "毒品"),
    ("冰毒", "毒品"),
    ("毒资", "毒品"),

    # --- 广告法极限词 ---
    ("国家级", "广告极限"),
    ("最高级", "广告极限"),
    ("最佳", "广告极限"),
    ("最好", "广告极限"),
    ("最大", "广告极限"),
    ("最优惠", "广告极限"),
    ("顶级", "广告极限"),
    ("极品", "广告极限"),
    ("终极", "广告极限"),
    ("首选", "广告极限"),
    ("第一", "广告极限"),
    ("唯一", "广告极限"),
    ("独家", "广告极限"),
    ("首创", "广告极限"),
    ("领先", "广告极限"),
    ("万能", "广告极限"),
    ("永久", "广告极限"),
    ("绝对", "广告极限"),
    ("绝对保证", "广告极限"),
    ("一定", "广告极限"),
    ("肯定", "广告极限"),
    ("实力", "广告极限"),
    ("主力", "广告极限"),
    ("保证赚钱", "广告极限"),
    ("稳赚", "广告极限"),
    ("躺赚", "广告极限"),
    ("零风险", "广告极限"),
    ("包过", "广告极限"),
    ("包治", "广告极限"),
    ("破天荒", "广告极限"),
    ("飙升", "广告极限"),
    ("天价", "广告极限"),
    ("王者", "广告极限"),
    ("至尊", "广告极限"),
    ("宝地", "广告极限"),
    ("宝盘", "广告极限"),
    ("经典", "广告极限"),
    ("传世", "广告极限"),
    ("盛世", "广告极限"),
    ("创世", "广告极限"),
    ("举世", "广告极限"),
    ("全球首发", "广告极限"),
    ("全国首发", "广告极限"),
    ("全网首发", "广告极限"),
    ("创始人", "广告极限"),
    ("指定", "广告极限"),
    ("官方", "广告极限"),
    ("权威机构", "广告极限"),
    ("国家机关", "广告极限"),
    ("世界顶级", "广告极限"),
    ("行业第一", "广告极限"),
    ("行业领军", "广告极限"),
    ("顶尖", "广告极限"),
    ("龄先", "广告极限"),
    ("领航", "广告极限"),
    ("引领", "广告极限"),
    ("引导", "广告极限"),
    ("榜首", "广告极限"),
    ("全球第一", "广告极限"),
    ("消费者放心", "广告极限"),
    ("放心选择", "广告极限"),
    ("买到就是赚到", "广告极限"),

    # --- 低俗/骂人 ---
    ("傻逼", "低俗"),
    ("傻B", "低俗"),
    ("傻X", "低俗"),
    ("神经病", "低俗"),
    ("瘋子", "低俗"),
    ("白痴", "低俗"),
    ("弱智", "低俗"),
    ("笨蛋", "低俗"),
    ("滚", "低俗"),
    ("滚开", "低俗"),
    ("滚蛋", "低俗"),
    ("去死", "低俗"),
    ("去死吧", "低俗"),
    ("死全家", "低俗"),
    ("卡巴拉扎", "低俗"),
    ("卡母", "低俗"),
    ("卡屌", "低俗"),
    ("日你", "低俗"),
    ("干你", "低俗"),
    ("艹", "低俗"),
    ("屎", "低俗"),
    ("尿", "低俗"),
    ("屁", "低俗"),
    ("屁股", "低俗"),
    ("屁眼", "低俗"),
    ("傻逼", "低俗"),
    ("二逼", "低俗"),
    ("二货", "低俗"),
    ("二百五", "低俗"),
    ("骚货", "低俗"),
    ("贱人", "低俗"),
    ("人渣", "低俗"),
    ("垃圾", "低俗"),
    ("废物", "低俗"),
    ("封建余寓", "低俗"),
    ("强国", "低俗"),
    ("游戏强国", "低俗"),
    ("日强", "低俗"),
    ("小日本", "低俗"),
    ("高丽棒", "低俗"),
    ("棒子", "低俗"),
    ("小棒子", "低俗"),
    ("图书", "低俗"),
]


class SensitiveChecker:
    """敏感词/违规内容检测器

    本地模式：基于内置词表做快速匹配，零成本。
    百度模式：通过百度AI内容审核API做深度检测，需配置环境变量。
    """

    def __init__(self, enable_baidu: bool = False):
        self.words = DEFAULT_SENSITIVE_WORDS
        self.enable_baidu = enable_baidu
        self._baidu_token: Optional[str] = None

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def check(self, text: str) -> dict:
        """
        检测文本中的敏感/违规内容

        返回：
            {
                "has_sensitive": bool,
                "hits": [
                    {"word": "...", "type": "...", "source": "local|baidu"},
                    ...
                ],
                "local_count": int,
                "baidu_count": int,
            }
        """
        if not text or not text.strip():
            return {
                "has_sensitive": False,
                "hits": [],
                "local_count": 0,
                "baidu_count": 0,
            }

        local_hits = self._check_local(text)
        baidu_hits: list[dict] = []

        if self.enable_baidu:
            try:
                baidu_hits = self._check_baidu(text)
            except Exception as e:
                # 百度API异常不应阻断正常生成流程
                print(f"[百度内容审核] 调用失败: {e}")

        all_hits = local_hits + baidu_hits
        return {
            "has_sensitive": len(all_hits) > 0,
            "hits": all_hits,
            "local_count": len(local_hits),
            "baidu_count": len(baidu_hits),
        }

    # ------------------------------------------------------------------
    # 本地词表检测
    # ------------------------------------------------------------------
    def _check_local(self, text: str) -> list[dict]:
        hits = []
        for word, word_type in self.words:
            if self._match_word(text, word):
                hits.append({"word": word, "type": word_type, "source": "local"})
        return hits

    @staticmethod
    def _match_word(text: str, word: str) -> bool:
        """
        智能词匹配：
        - 纯中文词：前后不能是汉字（避免匹配到词中）
        - 含英文/数字的词：用 word boundary
        """
        if not word:
            return False
        # 纯中文判断
        if re.match(r"^[\u4e00-\u9fff]+$", word):
            pattern = f"(?<![\u4e00-\u9fff]){re.escape(word)}(?![\u4e00-\u9fff])"
        else:
            pattern = f"(?<!\\w){re.escape(word)}(?!\\w)"
        return bool(re.search(pattern, text, re.IGNORECASE))

    # ------------------------------------------------------------------
    # 百度AI内容审核
    # ------------------------------------------------------------------
    def _check_baidu(self, text: str) -> list[dict]:
        """调用百度AI内容审核API，返回命中列表"""
        api_key = os.getenv("BAIDU_CENSOR_API_KEY", "").strip()
        secret_key = os.getenv("BAIDU_CENSOR_SECRET_KEY", "").strip()
        if not api_key or not secret_key:
            return []

        token = self._get_baidu_token(api_key, secret_key)
        if not token:
            return []

        url = f"https://aip.baidubce.com/rest/2.0/solution/v1/text_censor/v2/user_defined?access_token={token}"
        resp = requests.post(url, data={"text": text}, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        hits = []
        if data.get("conclusion") != "合规":
            for item in data.get("data", []):
                msg = item.get("msg", "未知风险")
                subtype = item.get("subtype", "未知")
                hits.append({
                    "word": f"{msg}({subtype})",
                    "type": item.get("type", "未知"),
                    "source": "baidu",
                })
        return hits

    def _get_baidu_token(self, api_key: str, secret_key: str) -> Optional[str]:
        """获取/缓存百度 access_token"""
        if self._baidu_token:
            return self._baidu_token

        url = (
            "https://aip.baidubce.com/oauth/2.0/token"
            f"?grant_type=client_credentials&client_id={api_key}&client_secret={secret_key}"
        )
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._baidu_token = data.get("access_token")
        return self._baidu_token


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------
def check_sensitive(text: str, enable_baidu: bool = False) -> dict:
    """一步式检测，无需实例化"""
    return SensitiveChecker(enable_baidu=enable_baidu).check(text)
