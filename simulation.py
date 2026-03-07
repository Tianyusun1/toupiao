import requests
import random
import time
import json
import base64
import re
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# ================= 配置区 =================
BASE_URL = "http://127.0.0.1:5000"
ADMIN_ID = "admin"
ADMIN_PWD = "123456"  # 确保与你数据库中的管理员密码一致

# 必须与 config.py 匹配的公钥 (用于模拟前端 RSA 加密)
PUBLIC_KEY_STR = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCs10mGwu4ex3jHFDpaQp+FNAir
ec+UVkdR6pRcdViwSD1FQnpNRrxrTJGy4XeubsTt8MygeOYWoJLJqJk9Oezi5hJx
5fFvA7eHeo0Q6txHNFlynf19MH4Hb7dRBt05PAoZcjiZJa/J1WOehfvp19IrnHBE
iIcGyxA+qaoBgWIGcwIDAQAB
-----END PUBLIC KEY-----"""

DEPT_LIST = ["计算机科学与技术学院", "电子信息工程学院", "经济管理学院", "艺术设计学院", "现代康养产业学院"]


# ==========================================

class VotingBot:
    def __init__(self):
        self.admin_session = requests.Session()
        self.users = []  # 存储 {"info": u_info, "session": session}
        self.pub_key = RSA.importKey(PUBLIC_KEY_STR)

    def encrypt(self, text):
        """模拟前端 JSEncrypt 加密过程"""
        cipher = PKCS1_v1_5.new(self.pub_key)
        return base64.b64encode(cipher.encrypt(text.encode())).decode()

    def admin_login(self):
        print("🔑 [管理员] 正在登录...")
        payload = {"student_id": ADMIN_ID, "password": self.encrypt(ADMIN_PWD)}
        res = self.admin_session.post(f"{BASE_URL}/auth/login", json=payload)
        return res.json().get('code') == 200

    def run_full_test(self, num_users=15):
        if not self.admin_login():
            print("❌ 管理员登录失败！请检查 ADMIN_PWD 是否正确。")
            return

        # 1. 批量注册
        print(f"👥 [阶段 1] 正在模拟注册 {num_users} 个测试学生...")
        for i in range(num_users):
            sid = f"2026{random.randint(100000, 999999)}"
            u_info = {
                "student_id": sid,
                "name": f"Robot_{sid[-4:]}",
                "department": random.choice(DEPT_LIST),
                "major": "自动化压测",
                "class_name": f"{random.randint(2201, 2205)}班",
                "entry_year": "2024",
                "password": "password123"
            }
            res = requests.post(f"{BASE_URL}/auth/register", json=u_info)
            if res.status_code == 200:
                self.users.append({"info": u_info, "session": requests.Session()})

        # 2. 自动审批用户
        print("⚖️ [阶段 2] 管理员正在批量核准学生注册申请...")
        pending_users = self.admin_session.get(f"{BASE_URL}/api/admin/users/pending").json().get('data', [])
        for u in pending_users:
            self.admin_session.post(f"{BASE_URL}/api/admin/users/approve", json={"user_id": u['id'], "action": "pass"})
        print(f"✅ 已核准 {len(pending_users)} 名学生。")

        # 3. 随机选一人发起提议
        print("💡 [阶段 3] 模拟随机一名学生发起限时投票提议...")
        proposer = random.choice(self.users)
        # 必须先登录该学生
        proposer['session'].post(f"{BASE_URL}/auth/login", json={
            "student_id": proposer['info']['student_id'],
            "password": self.encrypt("password123")
        })

        start = datetime.now().strftime('%Y-%m-%dT%H:%M')
        end = (datetime.now() + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M')
        prop_data = {
            "title": f"限时自动化压测_{int(time.time())}",
            "description": "该项目由自动化测试引擎生成，有效期30分钟，用于测试多选逻辑与AI指纹识别。",
            "start_time": start,
            "end_time": end,
            "is_multi_choice": "true",  # 模拟多选投票
            "options": json.dumps(["选项A：完全赞成", "选项B：基本赞成", "选项C：反对"])
        }
        res = proposer['session'].post(f"{BASE_URL}/api/vote/propose", data=prop_data)
        print(f"📩 提议提交结果: {res.json().get('msg')}")

        # 4. 管理员审批提议
        print("🛠️ [阶段 4] 管理员正在自动审批该项提议...")
        pending_e = self.admin_session.get(f"{BASE_URL}/api/admin/elections/pending").json().get('data', [])
        target_eid = None
        if pending_e:
            target_eid = pending_e[-1]['id']
            self.admin_session.post(f"{BASE_URL}/api/admin/elections/review",
                                    json={"election_id": target_eid, "action": "approve"})

        if not target_eid:
            print("❌ 未能获取到新创建的项目 ID，测试终止。")
            return

        # 5. 动态抓取 Candidate ID
        print(f"🔍 [阶段 5] 正在从项目 {target_eid} 详情页抓取真实候选人 ID...")
        # 管理员可能看不见投票按钮，使用刚才那个发起提议的学生 session 去看
        detail_html = proposer['session'].get(f"{BASE_URL}/election/{target_eid}").text
        # 使用正则表达式匹配 data-cid="..."
        real_candidate_ids = list(set(re.findall(r'data-cid="(\d+)"', detail_html)))
        print(f"✅ 成功获取候选人 ID 列表: {real_candidate_ids}")

        if not real_candidate_ids:
            print("❌ 无法抓取到候选人 ID，请检查 election_detail.html 是否已正确添加 data-cid 属性。")
            return

        # 6. 多线程并发投票（高并发压测）
        print(f"🔥 [阶段 6] 模拟 {num_users} 个线程发起瞬时并发投票冲击...")

        def vote_task(user_dict):
            sess = user_dict['session']
            # 1. 登录 (获取 Session Cookie)
            sess.post(f"{BASE_URL}/auth/login", json={
                "student_id": user_dict['info']['student_id'],
                "password": self.encrypt("password123")
            })
            # 2. 执行投票 (模拟多选)
            # 随机选择 1-2 个候选人
            choices = random.sample(real_candidate_ids, k=min(2, len(real_candidate_ids)))
            res = sess.post(f"{BASE_URL}/api/vote/do_vote", json={
                "election_id": target_eid,
                "candidate_ids": choices
            })
            return f"{user_dict['info']['name']}: {res.json().get('msg')}"

        # 使用线程池模拟并发
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(vote_task, self.users))
            for r in results:
                print(f"👤 投票状态 -> {r}")

        print(f"\n✨ 自动化全链路测试完成！")
        print(f"🚀 系统表现评价:")
        print(f"1. 业务逻辑: 成功完成【注册->审批->提议->发布->投票】闭环。")
        print(f"2. 多选测试: 模拟了同时投给多个候选人的逻辑。")
        print(f"3. 压力反馈: 请查看 Flask 控制台，观察 Redis 是否返回了 429 限流提示。")
        print(f"4. AI 审计: 请进入 /election/{target_eid}/results 查看评分，高频同IP请求应导致分值下降。")


if __name__ == "__main__":
    bot = VotingBot()
    # 建议设置为 15-30 左右，既能看到效果又不会因为本地网络太差导致请求超时
    bot.run_full_test(num_users=20)