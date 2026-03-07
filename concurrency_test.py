import requests
import base64
import time
import random
import json
import re
import concurrent.futures
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# ================= 压测配置 =================
BASE_URL = "http://127.0.0.1:5000"
ADMIN_ID = "admin"
ADMIN_PWD = "123456"  # 请务必确认你的管理员密码
CONCURRENT_THREADS = 50  # 瞬间并发数
# ============================================

PUBLIC_KEY_STR = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCs10mGwu4ex3jHFDpaQp+FNAir
ec+UVkdR6pRcdViwSD1FQnpNRrxrTJGy4XeubsTt8MygeOYWoJLJqJk9Oezi5hJx
5fFvA7eHeo0Q6txHNFlynf19MH4Hb7dRBt05PAoZcjiZJa/J1WOehfvp19IrnHBE
iIcGyxA+qaoBgWIGcwIDAQAB
-----END PUBLIC KEY-----"""


class ConcurrencyEngine:
    def __init__(self):
        self.admin_session = requests.Session()
        self.test_user_session = requests.Session()
        self.pub_key = RSA.importKey(PUBLIC_KEY_STR)
        self.test_sid = f"stress_{random.randint(1000, 9999)}"

    def encrypt(self, text):
        cipher = PKCS1_v1_5.new(self.pub_key)
        return base64.b64encode(cipher.encrypt(text.encode())).decode()

    def prepare_environment(self):
        print(f"🛠️ [1/3] 正在注册压测专用号: {self.test_sid}...")
        reg_payload = {
            "student_id": self.test_sid, "name": "并发压测机",
            "department": "计科院", "major": "压测专项",
            "class_name": "999班", "entry_year": "2026",
            "password": "password123"
        }
        requests.post(f"{BASE_URL}/auth/register", json=reg_payload)

        print("🛠️ [2/3] 管理员登录并自动审批该账号...")
        self.admin_session.post(f"{BASE_URL}/auth/login",
                                json={"student_id": ADMIN_ID, "password": self.encrypt(ADMIN_PWD)})
        pending = self.admin_session.get(f"{BASE_URL}/api/admin/users/pending").json().get('data', [])
        for u in pending:
            if u['student_id'] == self.test_sid:
                self.admin_session.post(f"{BASE_URL}/api/admin/users/approve",
                                        json={"user_id": u['id'], "action": "pass"})

        print("🛠️ [3/3] 压测账号登录...")
        self.test_user_session.post(f"{BASE_URL}/auth/login",
                                    json={"student_id": self.test_sid, "password": self.encrypt("password123")})

    def run_stress(self):
        print("🔍 正在扫描全量项目，寻找最近一个『进行中』的目标...")
        # 1. 获取所有项目列表
        all_elections = self.admin_session.get(f"{BASE_URL}/api/admin/elections/all").json().get('data', [])

        target_eid = None
        # 从列表末尾（最新的）开始往前找 active 状态的项目
        for e in reversed(all_elections):
            if e['status'] == 'active':
                target_eid = e['id']
                print(f"🎯 锁定目标项目 ID: {target_eid} (标题: {e['title']})")
                break

        if not target_eid:
            print("❌ 错误：翻遍了数据库，也没找到一个正在进行中的项目！请先发起一个投票。")
            return

        # 2. 动态抓取该项目的 Candidate ID
        print(f"📡 正在从详情页嗅探候选人 ID...")
        detail_html = self.test_user_session.get(f"{BASE_URL}/election/{target_eid}").text
        real_cids = list(set(re.findall(r'data-cid="(\d+)"', detail_html)))

        if not real_cids:
            print("❌ 错误：目标页面没有找到 data-cid 属性，无法执行有效投票。")
            return

        candidate_to_vote = [real_cids[0]]
        print(f"✅ 准备投给候选人 ID: {candidate_to_vote}")

        # 3. 发动爆发式冲击
        print(f"🔥 爆发！针对项目 {target_eid} 发动 {CONCURRENT_THREADS} 次瞬时冲击...")

        def task(i):
            # 记录请求发出的时间戳，用于观察瞬时性
            res = self.test_user_session.post(f"{BASE_URL}/api/vote/do_vote",
                                              json={"election_id": target_eid, "candidate_ids": candidate_to_vote})
            return res.status_code, res.json().get('msg')

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_THREADS) as executor:
            futures = [executor.submit(task, i) for i in range(CONCURRENT_THREADS)]
            for f in concurrent.futures.as_completed(futures):
                results.append(f.result())

        self.report(results, target_eid)

    def report(self, results, eid):
        success = [r for r in results if r[0] == 200]
        limited = [r for r in results if r[0] == 429]
        denied = [r for r in results if r[0] == 403]
        others = [r for r in results if r[0] not in [200, 429, 403]]

        print("\n" + "—" * 40)
        print(f"📊 瞬时并发审计报告 (项目ID: {eid})")
        print(f"✅ 穿透成功 (200 OK): {len(success)}")
        print(f"🛡️ Redis 拦截 (429 Limited): {len(limited)}")
        print(f"🚫 逻辑拒绝 (403 Voted): {len(denied)}")
        if others: print(f"⚠️ 其它异常: {len(others)} (详情: {others[0][1]})")

        print("\n🏆 技术评价:")
        if len(success) == 1:
            print("【完美】Redis 原子计数器工作正常，成功实现『万军丛中取一首』，有效抵御了并发刷票。")
        elif len(success) > 1:
            print(f"【风险】检测到有 {len(success)} 个请求穿透，存在竞态条件（Race Condition），请检查 Redis 逻辑。")
        elif len(denied) > 0:
            print("【提示】账号之前已参与过该投票，Redis 虽然拦截了大部分请求，但第一个请求被数据库约束挡住了。")
        else:
            print("【异常】所有请求均未成功进入业务层，请检查控制台日志。")
        print("—" * 40)


if __name__ == "__main__":
    engine = ConcurrencyEngine()
    engine.prepare_environment()
    engine.run_stress()