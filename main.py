import sonoff
import config

print('------ config ------')
print(config.username)
print(config.password)
print(config.api_region)

s = sonoff.Sonoff(config.username, config.password, config.api_region)
devices = s.get_devices()

# print('------ devices ------')
# print(devices)

# import ipdb
# ipdb.set_trace()

if devices:
    # We found a device, lets turn something on
    device_id = devices[2]['deviceid']
    name = devices[2]['name']
    switch = devices[2]['params']['switch']
    print('---------')
    print(name)
    print(device_id)
    print(switch)


# update config
config.api_region = s.get_api_region
config.user_apikey = s.get_user_apikey
config.bearer_token = s.get_bearer_token