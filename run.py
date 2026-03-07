from app import create_app

# 调用工厂函数，把我们刚才装配好的 app 实例拿出来
app = create_app()

if __name__ == '__main__':
    # 启动 Flask 内置服务器！
    # 开启 debug=True 模式，这样你以后修改代码保存后，服务器会自动重启，报错也会提示得更详细
    print(">>> 正在启动基于 Python 的在线投票系统后端服务...")
    app.run(host='127.0.0.1', port=5000, debug=True)