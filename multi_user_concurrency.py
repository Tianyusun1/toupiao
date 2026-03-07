import requests
import base64
import json
import random
import concurrent.futures
import time
import re
import sys
from datetime import datetime, timedelta
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# ================= 压测配置 =================
BASE_URL = "http://127.0.0.1:5000"
ADMIN_ID = "admin"
ADMIN_PWD = "123456"  # 确保与数据库一致
USER_COUNT = 100  # 100 人并发
# ============================================

PUBLIC_KEY_STR = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCs10mGwu4ex3jHFDpaQp+FNAir
ec+UVkdR6pRcdViwSD1FQnpNRrxrTJGy4XeubsTt8MygeOYWoJLJqJk9Oezi5hJx
5fFvA7eHeo0Q6txHNFlynf19MH4Hb7dRBt05PAoZcjiZJa/J1WOehfvp19IrnHBE
iIcGyxA+qaoBgWIGcwIDAQAB
-----END PUBLIC KEY-----"""


class StressTesterUltra:
    def __init__(self):
        self.pub_key = RSA.importKey(PUBLIC_KEY_STR)
        self.admin_session = requests.Session()
        self.user_sessions = []
        self.target_eid = None
        self.target_cid = None

    def encrypt(self, text):
        cipher = PKCS1_v1_5.new(self.pub_key)
        return base64.b64encode(cipher.encrypt(text.encode())).decode()

    def print_progress(self, iteration, total, prefix='', suffix='', length=40, fill='█'):
        percent = ("{0:.1f}").format(100 * (iteration / float(total)))
        filled_length = int(length * iteration // total)
        bar = fill * filled_length + '-' * (length - filled_length)
        sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
        sys.stdout.flush()
        if iteration == total: print()

    def prepare_environment(self):
        # 0. 管理员登录
        print("🔑 [准备] 管理员正在登录...")
        self.admin_session.post(f"{BASE_URL}/auth/login", json={
            "student_id": ADMIN_ID, "password": self.encrypt(ADMIN_PWD)
        })

        # 1. 自动创建一个“压测专项”投票项目
        print("🏗️ [核心] 正在自动发起一个 30 分钟限时压测项目...")
        start_time = datetime.now().strftime('%Y-%m-%dT%H:%M')
        end_time = (datetime.now() + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M')

        prop_payload = {
            "title": f"百人并发自动化压测_{int(time.time())}",
            "description": "系统自动生成的专项压测项目，用于验证高并发一致性。",
            "start_time": start_time,
            "end_time": end_time,
            "is_multi_choice": "false",
            "options": json.dumps(["压测候选人1", "压测候选人2"])
        }
        self.admin_session.post(f"{BASE_URL}/api/vote/propose", data=prop_payload)

        # 立即审批该项目
        print("⚖️ [审批] 自动通过压测项目审批...")
        pending_e = self.admin_session.get(f"{BASE_URL}/api/admin/elections/pending").json().get('data', [])
        if pending_e:
            self.target_eid = pending_e[-1]['id']
            self.admin_session.post(f"{BASE_URL}/api/admin/elections/review", json={
                "election_id": self.target_eid, "action": "approve"
            })
            print(f"✅ 压测项目已激活，ID: {self.target_eid}")
        else:
            print("❌ 错误：项目创建或审批失败！")
            return

        # 2. 批量注册机器人
        print(f"\n🚀 [阶段 1/3] 启动百人注册计划...")
        ts = int(time.time())
        for i in range(USER_COUNT):
            sid = f"robot_{i}_{ts}"
            reg_payload = {
                "student_id": sid, "name": f"Robot_{i}",
                "department": "人工智能学院", "major": "压测模型",
                "class_name": "2401班", "entry_year": "2024",
                "password": "password123"
            }
            requests.post(f"{BASE_URL}/auth/register", json=reg_payload)
            self.user_sessions.append({"sid": sid, "session": requests.Session()})
            self.print_progress(i + 1, USER_COUNT, prefix='注册进度', suffix='完成')

        print("\n⏳ 正在等待数据库写入同步 (1.5s)...")
        time.sleep(1.5)

        # 3. 批量审批用户（增强版：直到审批完 100 人为止）
        print("⚖️ [阶段 2/3] 管理员正在穿透审批这 100 个身份...")
        approved_count = 0
        my_sids = [u['sid'] for u in self.user_sessions]

        # 循环拉取待审批，直到注册的人全部过审
        while approved_count < USER_COUNT:
            pending_res = self.admin_session.get(f"{BASE_URL}/api/admin/users/pending").json()
            pending_list = pending_res.get('data', [])
            if not pending_list: break  # 没有待审了就跳出

            for u in pending_list:
                if u['student_id'] in my_sids:
                    self.admin_session.post(f"{BASE_URL}/api/admin/users/approve",
                                            json={"user_id": u['id'], "action": "pass"})
                    approved_count += 1
                    my_sids.remove(u['student_id'])  # 审过一个踢出一个
                    self.print_progress(approved_count, USER_COUNT, prefix='审批进度', suffix='完成')

        # 4. 批量模拟登录
        print("\n🔑 [阶段 3/3] 正在模拟 100 个 Session 登录获取授权...")
        for i, u in enumerate(self.user_sessions):
            u['session'].post(f"{BASE_URL}/auth/login", json={
                "student_id": u['sid'], "password": self.encrypt("password123")
            })
            self.print_progress(i + 1, USER_COUNT, prefix='登录进度', suffix='就绪')

    def run_burst(self):
        # 嗅探刚创建的项目候选人 ID
        print("\n📡 正在从项目详情页嗅探真实 Candidate ID...")
        detail_html = self.admin_session.get(f"{BASE_URL}/election/{self.target_eid}").text
        real_cids = list(set(re.findall(r'data-cid="(\d+)"', detail_html)))

        if not real_cids:
            print("❌ 错误：未能在页面找到 data-cid 属性，无法执行有效投票！")
            return

        self.target_cid = real_cids[0]
        print(f"🎯 目标锁定：项目 {self.target_eid} -> 候选人 {self.target_cid}")
        input("👉 准备好了吗？100 个 Session 已就绪。按回车键立即引爆高并发冲击...")

        def vote_task(u_dict):
            try:
                start = time.time()
                res = u_dict['session'].post(f"{BASE_URL}/api/vote/do_vote",
                                             json={"election_id": self.target_eid, "candidate_ids": [self.target_cid]})
                return res.status_code, time.time() - start
            except:
                return 500, 0

        # 100 线程瞬间爆发
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=USER_COUNT) as executor:
            futures = [executor.submit(vote_task, u) for u in self.user_sessions]
            for i, f in enumerate(concurrent.futures.as_completed(futures)):
                results.append(f.result())
                self.print_progress(i + 1, USER_COUNT, prefix='并发冲击进度', suffix='计票中')

        self.report(results)

    def report(self, results):
        success = [r for r in results if r[0] == 200]
        print("\n" + "=" * 45)
        print("📊 百人并发全自动闭环审计报告")
        print("=" * 45)
        print(f"🚀 模拟并发总用户: {USER_COUNT}")
        print(f"✅ 数据库成功计票: {len(success)}")
        print(f"❌ 失败或超时拦截: {USER_COUNT - len(success)}")
        print(f"⏱️ 平均响应延迟: {sum(r[1] for r in results) / len(results):.4f}s")
        print("\n🌟 结论：系统完美承载 100 并发。" if len(success) == USER_COUNT else "⚠️ 结论：检测到并发瓶颈。")
        print("=" * 45)


if __name__ == "__main__":
    tester = StressTesterUltra()
    tester.prepare_environment()
    tester.run_burst()