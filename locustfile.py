from locust import HttpUser, task, between

class VoteUser(HttpUser):
    wait_time = between(0.1, 0.5) # 模拟用户极快点击

    @task
    def do_vote(self):
        # 模拟投票接口调用
        self.client.post("/api/vote/do_vote", json={"election_id": 1, "candidate_ids": [1]})