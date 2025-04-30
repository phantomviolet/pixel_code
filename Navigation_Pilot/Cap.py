import requests
import time
import math

# ============ 기본 설정 ==============
APP_KEY = "4Gqu3WNznX1o60OkPK5Lo360oUutv4NNaVOWX1Xb"

startX = 127.027621  # 출발 경도
startY = 37.497942   # 출발 위도
endX = 127.041949    # 도착 경도
endY = 37.510146     # 도착 위도

# ========== 거리 계산 함수 ===========
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # 지구 반지름 (m)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = math.sin(d_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c  # 거리 (미터)

# ========== 경로 요청 ==========
url = "https://apis.openapi.sk.com/tmap/routes/pedestrian?version=1"
headers = {
    "appKey": APP_KEY,
    "Content-Type": "application/json"
}
payload = {
    "startX": str(startX),
    "startY": str(startY),
    "endX": str(endX),
    "endY": str(endY),
    "reqCoordType": "WGS84GEO",
    "resCoordType": "WGS84GEO",
    "startName": "출발지",
    "endName": "도착지"
}

response = requests.post(url, headers=headers, json=payload)

if response.status_code != 200:
    print("Error:", response.status_code, response.text)
    exit()

data = response.json()
features = data["features"]

# ====== 회전 포인트 저장 ======
waypoints = []
for feature in features:
    properties = feature["properties"]
    geometry = feature["geometry"]
    coords = geometry["coordinates"]
    
    if "turnType" in properties and properties["turnType"] != 0:
        if geometry["type"] == "Point":
            lon, lat = coords
        else:
            lon, lat = coords[0]
        
        waypoints.append({
            "lat": lat,
            "lon": lon,
            "turnType": properties["turnType"]
        })

print(f"회전 포인트 개수: {len(waypoints)}개")

# ====== 가짜 현재 위치 이동 (시뮬레이션) ======
current_lat = startY
current_lon = startX

# 첫 이동 방향 설정
if waypoints:
    next_target = waypoints[0]
else:
    next_target = {"lat": endY, "lon": endX}

step_lat = (next_target["lat"] - current_lat) / 50
step_lon = (next_target["lon"] - current_lon) / 50

# ====== 메인 루프 ======
while True:
    dist = haversine(current_lat, current_lon, next_target["lat"], next_target["lon"])
    print(f"현재 위치: ({current_lat:.6f}, {current_lon:.6f}), 다음 지점까지 거리: {dist:.2f}m")

    if dist < 5:  # 5m 이내로 가까워지면
        if "turnType" in next_target:
            turnType = next_target["turnType"]
            if turnType == 211:
                print("우회전 하세요!")
            elif turnType == 212:
                print("좌회전 하세요!")

            waypoints.pop(0)  # 해당 회전 포인트 제거

        if waypoints:
            next_target = waypoints[0]
        else:
            next_target = {"lat": endY, "lon": endX}

        # 새로운 방향 다시 설정
        step_lat = (next_target["lat"] - current_lat) / 50
        step_lon = (next_target["lon"] - current_lon) / 50

    # 도착지점에 거의 도달했으면 종료
    final_dist = haversine(current_lat, current_lon, endY, endX)
    if final_dist < 5:
        print(" 도착했습니다!")
        break

    # 이동
    current_lat += step_lat
    current_lon += step_lon

    time.sleep(1)  # 이동 속도 조정 (빠르게 하고 싶으면 줄여도 됨)

