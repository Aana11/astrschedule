import json
import os
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from astrbot.api.all import *

# 数据存储文件路径
DATA_FILE = "course_data.json"

@register("course_reminder", "YourName", "课程表提醒插件", "1.0.0")
class CourseReminderPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.scheduler = AsyncIOScheduler()
        self.data = self.load_data()
        
        # 每分钟检查一次提醒
        self.scheduler.add_job(self.check_reminders, 'interval', minutes=1)
        self.scheduler.start()

    def load_data(self):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_data(self):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

    async def check_reminders(self):
        """
        后台定时任务：检查是否有30分钟后开始的课程
        """
        now = datetime.now()
        # 目标时间：当前时间 + 30分钟
        target_time = now + timedelta(minutes=30)
        
        # 获取当前的星期 (1=周一, 7=周日)
        current_weekday = now.isoweekday()
        # 获取目标时分，例如 "14:30"
        target_time_str = target_time.strftime("%H:%M")

        # 遍历所有用户的数据
        for user_id, user_data in self.data.items():
            courses = user_data.get("courses", [])
            
            # 必须的信息：用于发送消息
            provider_id = user_data.get("provider_id")
            conversation_id = user_data.get("conversation_id") # 可能是群ID或私聊ID
            
            if not provider_id or not conversation_id:
                continue

            for course in courses:
                # 比对星期和时间
                if course['day'] == current_weekday and course['time'] == target_time_str:
                    # 触发提醒
                    await self.send_reminder(provider_id, conversation_id, user_id, course)

    async def send_reminder(self, provider_id, conversation_id, user_id, course):
        """
        发送主动消息提醒
        """
        provider = self.context.get_provider(provider_id)
        if not provider:
            return
            
        msg = (
            f"🔔 上课提醒！\n"
            f"----------------\n"
            f"课程：{course['name']}\n"
            f"地点：{course['location']}\n"
            f"时间：{course['time']} (30分钟后)\n"
            f"----------------\n"
            f"请做好准备哦！"
        )
        
        # 调用 AstrBot 的发送接口
        # 注意：这里假设是 OneBot/QQ 环境，直接发给对应的 conversation_id
        try:
            await provider.send_message(conversation_id, msg)
        except Exception as e:
            # 记录错误日志，防止发送失败导致崩溃
            print(f"[CourseReminder] 发送提醒失败: {e}")

    @command("add_course")
    async def add_course(self, event: AstrMessageEvent, day: str, time_str: str, name: str, location: str):
        """
        添加课程
        用法: /add_course 周一 14:00 高等数学 教学楼301
        """
        user_id = event.get_sender_id()
        # 保存会话信息以便后续主动发消息
        provider_id = event.session.provider.id
        # 获取会话ID（如果是群聊就是群ID，私聊就是用户ID）
        conversation_id = event.message_obj.group_id if event.message_obj.group_id else user_id

        # 简单的星期转换
        day_map = {"周一": 1, "周二": 2, "周三": 3, "周四": 4, "周五": 5, "周六": 6, "周日": 7, 
                   "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7}
        
        wd = day_map.get(day)
        if not wd:
            yield event.plain_result("❌ 星期格式错误，请输入“周一”或数字1-7。")
            return

        # 时间格式验证 (简单的长度检查，最好用 datetime parse)
        if ":" not in time_str:
             yield event.plain_result("❌ 时间格式错误，请输入如 08:00 或 14:30。")
             return

        # 初始化用户数据
        if user_id not in self.data:
            self.data[user_id] = {
                "provider_id": provider_id,
                "conversation_id": conversation_id,
                "courses": []
            }

        new_course = {
            "day": wd,
            "time": time_str,
            "name": name,
            "location": location
        }
        
        # 更新 provider_id 和 conversation_id 以防变动
        self.data[user_id]["provider_id"] = provider_id
        self.data[user_id]["conversation_id"] = conversation_id
        
        self.data[user_id]["courses"].append(new_course)
        # 按时间排序
        self.data[user_id]["courses"].sort(key=lambda x: (x['day'], x['time']))
        
        self.save_data()
        yield event.plain_result(f"✅ 已添加课程：{name} ({day} {time_str})")

    @command("my_courses")
    async def list_courses(self, event: AstrMessageEvent):
        """
        查看我的课程表
        """
        user_id = event.get_sender_id()
        if user_id not in self.data or not self.data[user_id]["courses"]:
            yield event.plain_result("📭 你还没有录入课程。使用 /add_course 添加。")
            return

        courses = self.data[user_id]["courses"]
        week_days = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
        
        msg = ["📅 我的课程表："]
        for idx, c in enumerate(courses):
            msg.append(f"{idx+1}. {week_days[c['day']]} {c['time']} | {c['name']} @ {c['location']}")
        
        yield event.plain_result("\n".join(msg))

    @command("del_course")
    async def delete_course(self, event: AstrMessageEvent, index: int):
        """
        删除课程
        用法: /del_course 1 (序号对应 /my_courses 中的编号)
        """
        user_id = event.get_sender_id()
        if user_id not in self.data or not self.data[user_id]["courses"]:
            yield event.plain_result("📭 无课程可删除。")
            return

        courses = self.data[user_id]["courses"]
        if index < 1 or index > len(courses):
            yield event.plain_result("❌ 序号无效。")
            return

        removed = courses.pop(index - 1)
        self.save_data()
        yield event.plain_result(f"🗑️ 已删除课程：{removed['name']}")