import json
import os
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from astrbot.api.all import *

DATA_FILE = "course_data.json"

@register("course_reminder", "YourName", "课程表提醒插件", "1.1.0")
class CourseReminderPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.scheduler = AsyncIOScheduler()
        self.data = self.load_data()
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
        now = datetime.now()
        target_time = now + timedelta(minutes=30)
        current_weekday = now.isoweekday()
        target_time_str = target_time.strftime("%H:%M")

        for user_id, user_data in self.data.items():
            courses = user_data.get("courses", [])
            provider_id = user_data.get("provider_id")
            conversation_id = user_data.get("conversation_id")
            
            if not provider_id or not conversation_id:
                continue

            for course in courses:
                if course['day'] == current_weekday and course['time'] == target_time_str:
                    await self.send_reminder(provider_id, conversation_id, user_id, course)

    async def send_reminder(self, provider_id, conversation_id, user_id, course):
        provider = self.context.get_provider(provider_id)
        if not provider:
            return
        msg = f"🔔 上课提醒！\n----------------\n课程：{course['name']}\n地点：{course['location']}\n时间：{course['time']} (30分钟后)\n----------------"
        try:
            await provider.send_message(conversation_id, msg)
        except Exception as e:
            print(f"[CourseReminder] Error: {e}")

    @command("add_course")
    async def add_course(self, event: AstrMessageEvent, day: str, time_str: str, name: str, location: str):
        """单条添加: /add_course 周一 14:00 数学 教室1"""
        # ... (此处省略重复代码，逻辑同上一个版本，为节省篇幅只展示新功能) ...
        # 请保留原来 add_course 的完整逻辑，或者只用下面的 import_json 也可以
        await self._add_single_course(event, day, time_str, name, location)

    async def _add_single_course(self, event, day, time_str, name, location):
        # 辅助函数：复用添加逻辑
        user_id = event.get_sender_id()
        provider_id = event.session.provider.id
        conversation_id = event.message_obj.group_id if event.message_obj.group_id else user_id
        
        day_map = {"周一": 1, "周二": 2, "周三": 3, "周四": 4, "周五": 5, "周六": 6, "周日": 7}
        wd = day_map.get(day) if day in day_map else int(day) if day.isdigit() else None
        
        if not wd or ":" not in time_str:
            return False

        if user_id not in self.data:
            self.data[user_id] = {"provider_id": provider_id, "conversation_id": conversation_id, "courses": []}
        
        self.data[user_id]["provider_id"] = provider_id
        self.data[user_id]["conversation_id"] = conversation_id
        
        new_course = {"day": wd, "time": time_str, "name": name, "location": location}
        self.data[user_id]["courses"].append(new_course)
        self.data[user_id]["courses"].sort(key=lambda x: (x['day'], x['time']))
        self.save_data()
        return True

    @command("my_courses")
    async def list_courses(self, event: AstrMessageEvent):
        """查看课表"""
        user_id = event.get_sender_id()
        if user_id not in self.data or not self.data[user_id]["courses"]:
            yield event.plain_result("📭 空空如也。")
            return
        courses = self.data[user_id]["courses"]
        week_days = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
        msg = ["📅 我的课程表："]
        for idx, c in enumerate(courses):
            msg.append(f"{idx+1}. {week_days[c['day']]} {c['time']} | {c['name']} @ {c['location']}")
        yield event.plain_result("\n".join(msg))

    @command("del_course")
    async def delete_course(self, event: AstrMessageEvent, index: int):
        """删除课程"""
        user_id = event.get_sender_id()
        if user_id in self.data and 0 < index <= len(self.data[user_id]["courses"]):
            removed = self.data[user_id]["courses"].pop(index - 1)
            self.save_data()
            yield event.plain_result(f"🗑️ 已删除：{removed['name']}")
        else:
            yield event.plain_result("❌ 序号无效。")

    @command("import_json")
    async def import_json(self, event: AstrMessageEvent, json_str: str):
        """
        [高级] 批量导入 JSON 数据
        用法: /import_json [{"day":1,"time":"08:00","name":"英语","location":"A101"}]
        """
        try:
            # 尝试清洗数据，防止用户输入的 JSON 包含 markdown 代码块标记
            cleaned_json = json_str.replace("```json", "").replace("```", "").strip()
            course_list = json.loads(cleaned_json)
            
            if not isinstance(course_list, list):
                yield event.plain_result("❌ 数据格式错误：必须是列表 list")
                return

            success_count = 0
            # 这里的逻辑稍微简化，直接借用 add_single_course 的逻辑核心，或者手动写入
            # 为了方便，我们直接操作数据
            user_id = event.get_sender_id()
            provider_id = event.session.provider.id
            conversation_id = event.message_obj.group_id if event.message_obj.group_id else user_id

            if user_id not in self.data:
                self.data[user_id] = {"provider_id": provider_id, "conversation_id": conversation_id, "courses": []}
            
            # 更新会话ID
            self.data[user_id]["provider_id"] = provider_id
            self.data[user_id]["conversation_id"] = conversation_id

            for item in course_list:
                # 数据校验
                if all(k in item for k in ("day", "time", "name", "location")):
                    # 确保 day 是 int
                    if isinstance(item["day"], str):
                        day_map = {"周一": 1, "周二": 2, "周三": 3, "周四": 4, "周五": 5, "周六": 6, "周日": 7}
                        item["day"] = day_map.get(item["day"], 1)
                    
                    self.data[user_id]["courses"].append(item)
                    success_count += 1
            
            # 排序并保存
            self.data[user_id]["courses"].sort(key=lambda x: (x['day'], x['time']))
            self.save_data()
            
            yield event.plain_result(f"✅ 成功导入 {success_count} 节课程！")

        except json.JSONDecodeError:
            yield event.plain_result("❌ JSON 格式解析失败，请检查格式。")
        except Exception as e:
            yield event.plain_result(f"❌ 发生错误: {str(e)}")
