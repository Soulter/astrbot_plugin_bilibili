"""
UI 开发模式模块
用于本地预览和调试 Bilibili 插件的 UI
"""

from .mock_data import (
    MockDataGenerator,
    get_all_mock_scenarios,
    get_scenarios_by_category,
    get_scenario_by_name,
    get_scenario_names,
)

__all__ = [
    "MockDataGenerator",
    "get_all_mock_scenarios", 
    "get_scenarios_by_category",
    "get_scenario_by_name",
    "get_scenario_names",
]

