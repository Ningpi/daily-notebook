# -*- coding: utf-8 -*-
"""
每日记事本 —— 便签配色主题

全部走低饱和「奶油 / 莫兰迪」路线：底色明度在 84%~92%（相当于往纯白里
调进一点点色，不是荧光色），正文对比度 10:1 以上，长时间盯着不刺眼。
强调色压暗到能承白色文字（「发送」按钮），同时保持饱和度克制。

每套主题 8 个色：
  bg     便签纸底色        head   标题栏
  line   分隔线            sub    次要文字
  accent 强调色（选中/按钮） text   主要文字
  row2   列表隔行底色      bubble 用户气泡
"""

THEMES = [
    {
        "id": "cream",
        "name": "奶油黄",
        "bg": "#FBF3D5", "head": "#F6E6A8", "line": "#E6D9A8",
        "sub": "#857A5E", "accent": "#8E7216", "text": "#3D3428",
        "row2": "#FDF8E4", "bubble": "#F5E4A8",
    },
    {
        "id": "rice",
        "name": "米白",
        "bg": "#F7F3E8", "head": "#ECE4D2", "line": "#DCD3BD",
        "sub": "#82806F", "accent": "#8A7248", "text": "#3C372E",
        "row2": "#FBF8F0", "bubble": "#EBE2CC",
    },
    {
        "id": "mint",
        "name": "薄荷",
        "bg": "#E8F3EA", "head": "#D2E8D6", "line": "#C0DCC5",
        "sub": "#63796A", "accent": "#4A8560", "text": "#2F3B32",
        "row2": "#F0F8F1", "bubble": "#D3EADA",
    },
    {
        "id": "mist",
        "name": "雾蓝",
        "bg": "#E7EFF5", "head": "#D2E1ED", "line": "#BFD3E3",
        "sub": "#61748A", "accent": "#4C7595", "text": "#2C3642",
        "row2": "#EFF5F9", "bubble": "#D3E3EF",
    },
    {
        "id": "lotus",
        "name": "藕粉",
        "bg": "#F7EBEE", "head": "#EFD5DB", "line": "#E1C3CB",
        "sub": "#846873", "accent": "#A25F76", "text": "#3E3034",
        "row2": "#FBF3F5", "bubble": "#F0D6DD",
    },
    {
        "id": "apricot",
        "name": "浅杏",
        "bg": "#F9EEDF", "head": "#F2DCC1", "line": "#E5CBAE",
        "sub": "#87735A", "accent": "#A2723F", "text": "#3F362B",
        "row2": "#FCF5EB", "bubble": "#F2DBBE",
    },
    {
        "id": "sage",
        "name": "鼠尾草绿",
        "bg": "#EDEFE3", "head": "#DDE1C8", "line": "#CBD1B4",
        "sub": "#757C5F", "accent": "#6C7D47", "text": "#373B2D",
        "row2": "#F4F5EC", "bubble": "#DDE1C6",
    },
    {
        "id": "lilac",
        "name": "淡紫",
        "bg": "#F0EBF6", "head": "#E0D7EC", "line": "#CFC4E0",
        "sub": "#766B89", "accent": "#73629A", "text": "#33303C",
        "row2": "#F7F3FB", "bubble": "#E2D8EE",
    },
]

DEFAULT_ID = "cream"


def get(theme_id):
    for t in THEMES:
        if t["id"] == theme_id:
            return t
    return THEMES[0]


def get_id(theme_id):
    return get(theme_id)["id"]


def ids():
    return [t["id"] for t in THEMES]


def names():
    return [t["name"] for t in THEMES]
