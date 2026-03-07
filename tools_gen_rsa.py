from Crypto.PublicKey import RSA

# 生成 1024 位长的密钥对（投票系统够用了，速度快）
key = RSA.generate(1024)

# 提取私钥 (存到 config.py)
private_key = key.export_key().decode('utf-8')
print("-" * 20 + " 后端专用：私钥 (放入 config.py) " + "-" * 20)
print(private_key)

# 提取公钥 (存到 login.html)
public_key = key.publickey().export_key().decode('utf-8')
print("\n" + "-" * 20 + " 前端专用：公钥 (放入 login.html) " + "-" * 20)
print(public_key)