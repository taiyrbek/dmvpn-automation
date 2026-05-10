from jinja2 import Template
import getpass
import re
import time
import yaml
from netmiko import ConnectHandler
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

username = input('Введите логин : ')
password = getpass.getpass('Введите пароль от учетной записи : ')
enable_secret = getpass.getpass('Введите enable пароль  : ')

def verify_net_health(device_ssh, router):
    print(f"\n{'-'*50}")
    print(f"📊 ОТЧЕТ ПО УСТРОЙСТВУ: {router}")
    print(f"{'-'*50}")
    try:
        with ConnectHandler(**device_ssh) as ssh:
            ssh.enable()
            ike = ssh.send_command('show crypto ikev2 sa | i READY')
            ipsec = ssh.send_command('show crypto ipsec sa | i Status')
            
            ike_count = ike.count("READY")
            if ike_count > 0 :
                print(f"Сессии установлены {ike_count} шт.")
            else:
                print(f"Ни одного туннеля не установлено {ike_count}")
            if "ACTIVE" in ipsec:
                ssh1 = ssh.send_command("show crypto ipsec sa  ")
                pattern =r"current_peer\s+([\d\.]+).*?#pkts encaps:\s+(\d+),.*?#pkts decaps:\s+(\d+),"
                print(f"(IPSEC)в статусе ACTIVE")
                
                peers_data = re.findall(pattern, ssh1, re.DOTALL)
                
                if peers_data:
                    print(f"{'Айпи пира': <16} | {'tx': <16} | {'rx': <16}")
                    print(f"{'-'*16}-+-{'-'*16}-+-{'-'*16}")
                    for peer_ip,tx,rx in peers_data:
                        
                        print(f"{peer_ip:<16} | {tx: <16} | {rx: <16}")
                        if tx == "0" and rx == "0":
                            print(f"Туннели в состоянии ACTIVE, но пакеты не ходят!")
            else:
                print(f"Внимание : IPsec активных сессий нет !")
            nhrp = ssh.send_command('show dmvpn | i UP')
            nhrp_count = nhrp.count("UP")
            if nhrp_count > 0:
                print(f"DMVPN-NHRP зарегистрировано пиров: {nhrp_count}")
            else:
                print(f"DMVPN-NHRP пиры не зарегистрированы !")
            ospf = ssh.send_command('show ip ospf neighbor | i  FULL')
            ospf_count = ospf.count("FULL")
            if ospf_count >0:
                print(f"OSPF соседи в состоянии FULL: {ospf_count}")
            else:
                print(f"OSPF соседей в состоянии FULL не найдено !")
    except NetmikoTimeoutException:
        print(f"Не можем подключиться на роутер {router } (таймаут)")
    except NetmikoAuthenticationException:
        print(f"Неверные данные логин/пароль на {router }")
    except Exception as e:
        print(f"Вышла текущая ошибка {e} с  роутером {router } ")

with open('information.yaml') as f:
    full_data = yaml.safe_load(f)
    net_device = full_data['routers']
    global_settings = full_data['global']
ip_list = []

for r in net_device:
    r['global'] = global_settings
    if r['role'] == 'hub':
        template_file = 'hub.j2'
        for tun in r['tunnels']:
            tunnel_ip = tun['ip']
            nbma_intf = tun['tunnel_source']
            net_id = tun['nhrp_network_id']
        
            real_ip = None
            for intf in r['interface']:
                if intf['name'] == nbma_intf:
                    real_ip = intf['ip']
            if real_ip and tunnel_ip:
                ip_list.append({
                    'tunnel_ip': tunnel_ip,
                    'nbma_ip':real_ip,
                    'nhrp_id':net_id
                })
        
if not ip_list:
    print(f'В списке  нету настройки хабов !')
else:
    print(f"✅ Хабы найдены. База IP сформирована: {len(ip_list)} туннелей.")

for r in net_device:
    if r['role'] == 'hub':
        template_file = 'hub.j2'
    elif r['role'] == 'spoke':
        template_file = 'spoke.j2'
        r['hub'] = ip_list
        
    else:
        continue
    device_ssh = {
        
        'device_type':'cisco_ios',
        'username':username,
        'password':password,
        'secret':enable_secret,
        'host': r['ip_management']
    }

    with open (template_file) as f:

        first_temp = Template(f.read())
        finall_text = first_temp.render(**r)
    try:
        with  ConnectHandler(**device_ssh) as ssh:
            ssh.enable()
            output = ssh.send_config_set(finall_text.splitlines())
            print(output)
            print(f"Конфигурация приминилась успешно !")
            print(f"смотрим состояние туннелей ")
            dmvpn_status = ssh.send_command("show dmvpn | i up")
            if dmvpn_status:
                print(dmvpn_status)
            else:
                print(f"Туннели поднимаются")
            print("-" * 50)
            

    except Exception as e:
        print(f'есть проблема, ошибка  c роутером {r["hostname"]} {e}')  

print(f"Финанльная проверка сети ...")
wait_time = 40
for i in range(wait_time, 0, -1):
    print(f"\rосталось столько секунд {i:02d} ... ", end="", flush=True)
    time.sleep(1)

for r in net_device:
    device_ssh = {
        'device_type':'cisco_ios',
        'username':username,
        'password':password,
        'secret':enable_secret,
        'host': r['ip_management']
    }
    verify_net_health(device_ssh, r['hostname'])
print(f"Автоматизация успешно завершена !")


     


