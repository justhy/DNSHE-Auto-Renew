import requests
import json
import os
from datetime import datetime

# 从环境变量获取配置
API_KEY = os.environ.get('API_KEY')
API_SECRET = os.environ.get('API_SECRET')
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID')

BASE_URL = "https://api005.dnshe.com/index.php?m=domain_hub"

# 续期阈值：到期时间小于该天数则执行续期
RENEW_THRESHOLD_DAYS = 180

# TG推送
def sendTgBot(content):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("未配置推送信息，跳过推送")
        return
    
    headers={
            'Content-Type': 'application/json'
            }
    data={
         'chat_id':TG_CHAT_ID,
         'text':content,
         'parse_mode':'HTML'
         }  
    for retry_ in range(4):  
        posttext=requests.post(r'https://api.telegram.org/bot'+TG_BOT_TOKEN+r'/sendMessage',headers=headers,data=json.dumps(data))
        if posttext.status_code < 300:
             print('tg推送成功')
             break
        else:
            if retry_ == 3:
                print('tg推送失败')
    print('')


def main():
    headers = {
        "X-API-Key": API_KEY,
        "X-API-Secret": API_SECRET,
        "Content-Type": "application/json"
    }

    # 1. 获取所有子域名（显式请求到期时间字段）
    list_url = f"{BASE_URL}&endpoint=subdomains&action=list&fields=id,subdomain,rootdomain,full_domain,status,expires_at,never_expires"
    try:
        resp = requests.get(list_url, headers=headers)
        subdomains = resp.json().get('subdomains', [])
    except Exception as e:
        sendTgBot(f"获取域名列表失败: {str(e)}")
        return

    today = datetime.now()
    renewal_results = []  # 第一段：本次续期结果
    expiry_info = {}      # 第二段：所有域名到期时间（以域名为键，续期后可更新）

    # 2. 遍历域名，检查到期时间并选择性续期
    for domain in subdomains:
        domain_id = domain['id']
        full_domain = domain['full_domain']
        expires_at_str = domain.get('expires_at')
        never_expires = domain.get('never_expires', 0)

        # 检查是否为永不过期域名
        if never_expires:
            expiry_info[full_domain] = f"{full_domain}: 到期时间 永久有效"
            renewal_results.append(f"⏭️ {full_domain}: 已设置为永不过期，跳过续期")
            continue

        # 计算剩余天数
        expires_at = None
        if expires_at_str:
            expires_at = datetime.strptime(expires_at_str, '%Y-%m-%d %H:%M:%S')
            days_remaining = (expires_at - today).days
        else:
            days_remaining = None

        # 记录到期信息（第二段用）
        if days_remaining is not None:
            expiry_info[full_domain] = f"{full_domain}: 到期时间 {expires_at_str} (剩余 {days_remaining}天)"
        else:
            expiry_info[full_domain] = f"{full_domain}: 到期时间 未知"

        # 判断是否需要续期：剩余天数 < 180天 才续期
        if days_remaining is not None and days_remaining >= RENEW_THRESHOLD_DAYS:
            renewal_results.append(f"⏭️ {full_domain}: 剩余 {days_remaining}天 >= {RENEW_THRESHOLD_DAYS}天，跳过续期")
            continue

        # 执行续期
        renew_url = f"{BASE_URL}&endpoint=subdomains&action=renew"
        payload = {"subdomain_id": domain_id}

        try:
            r_resp = requests.post(renew_url, headers=headers, json=payload).json()
            if r_resp.get('success'):
                new_expiry = r_resp.get('new_expires_at', '未知')
                charged = r_resp.get('charged_amount', 0)
                renewal_results.append(f"✅ {full_domain}: 续期成功 (新到期: {new_expiry}, 消耗: {charged}积分)")
                # 同步更新第二段的到期时间为续期后的新时间
                if new_expiry != '未知':
                    try:
                        new_expires_at = datetime.strptime(new_expiry, '%Y-%m-%d %H:%M:%S')
                        new_days_remaining = (new_expires_at - today).days
                        expiry_info[full_domain] = f"{full_domain}: 到期时间 {new_expiry} (剩余 {new_days_remaining}天)"
                    except ValueError:
                        expiry_info[full_domain] = f"{full_domain}: 到期时间 {new_expiry}"
                else:
                    expiry_info[full_domain] = f"{full_domain}: 到期时间 {new_expiry}"
            else:
                msg = r_resp.get('message', '未知错误')
                renewal_results.append(f"❌ {full_domain}: 续期失败 ({msg})")
        except Exception as e:
            renewal_results.append(f"❌ {full_domain}: 请求异常 ({str(e)})")

    # 3. 构建两段式通知消息
    message_parts = []
    message_parts.append("=== 本次续期结果 ===")
    if renewal_results:
        message_parts.extend(renewal_results)
    else:
        message_parts.append("（所有域名剩余天数 >= 180天，本次无需续期）")

    message_parts.append("")
    message_parts.append("=== 所有域名到期时间 ===")
    message_parts.extend(expiry_info.values())

    message = "\n".join(message_parts)
    print(message)
    sendTgBot(message)

if __name__ == "__main__":
    main()
