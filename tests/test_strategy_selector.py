"""
策略选择器测试

测试内容类型识别和策略选择
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.planning.strategy import ContentType, Strategy, STRATEGIES


class TestContentType(unittest.TestCase):
    """测试内容类型枚举"""
    
    def test_content_types(self):
        """测试所有内容类型"""
        self.assertEqual(ContentType.DEEP_DIVE.value, "深度长文")
        self.assertEqual(ContentType.HOT_NEWS.value, "热点快讯")
        self.assertEqual(ContentType.TUTORIAL.value, "实战教程")
        self.assertEqual(ContentType.REVIEW.value, "评测对比")
        self.assertEqual(ContentType.OPINION.value, "观点评论")
        self.assertEqual(ContentType.UNKNOWN.value, "未知类型")


class TestStrategies(unittest.TestCase):
    """测试预设策略"""
    
    def test_strategy_attributes(self):
        """测试策略属性"""
        strategy = STRATEGIES[ContentType.DEEP_DIVE]
        self.assertEqual(strategy.name, "深度研究")
        self.assertEqual(strategy.content_type, ContentType.DEEP_DIVE)
        self.assertIn("search", strategy.steps)
        self.assertIn("generate", strategy.steps)
        self.assertGreater(strategy.threshold, 0)
    
    def test_all_strategies_have_steps(self):
        """测试所有策略都有步骤"""
        for content_type, strategy in STRATEGIES.items():
            with self.subTest(content_type=content_type):
                self.assertGreater(len(strategy.steps), 0)
                self.assertGreater(len(strategy.tools), 0)


if __name__ == "__main__":
    unittest.main()
