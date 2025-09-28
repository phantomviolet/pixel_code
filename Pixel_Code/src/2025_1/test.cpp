#include <iostream>
#include <cstdlib>
#include <ctime>
#include <iomanip>
#include <fstream>
using namespace std;

// 위험 수준을 3단계로 정의
enum State {
    SAFE,
    WARNING,
    DECELERATE
};

const float MAX_DECELERATION = 3.0; // m/s²
const float MAX_SPEED = 5.56;       // 최고속도 20km/h = 5.56m/s

// 제동 거리 계산
float BrakingDistance(float speed) {
    return (speed * speed) / (2 * MAX_DECELERATION);
}

// TTC 계산
float getTTC(float distance, float speed) {
    if (speed <= 0.0) return 9999.0;
    return distance / speed;
}


// 위험 수준 판단
State updateState(float distance, float speed, float ttc) {
    static int ttc_sustained_count = 0;

    if (speed < 0.5) {
        ttc_sustained_count = 0;
        return SAFE;
    }

    if (ttc < 1.2) ttc_sustained_count++;
    else ttc_sustained_count = 0;

    if ((ttc < 1.2 && ttc_sustained_count >= 2) || distance < 1.5) {
        return DECELERATE;
    } 
    else if (ttc < 2.0) {
        return WARNING;
    } 
    else {
        return SAFE;
    }
}

// 상태를 문자열로 변환
string stateToString(State state) {
    switch(state) {
        case SAFE: 
            return "SAFE";
        case WARNING: 
            return "WARNING";
        case DECELERATE: 
            return "DECELERATE";
        default: 
            return "UNKNOWN";
    }
}

// 랜덤 실수 생성
float randomFloat(float min, float max) {
    return min + static_cast<float>(rand()) / (static_cast<float>(RAND_MAX / (max - min)));
}

int main() {
    srand(static_cast<unsigned int>(time(0)));  // 랜덤 시드 초기화

    cout << "===============================" << endl;

    int testCount;
    cout << "테스트 횟수: ";
    cin >> testCount;

    ofstream resultFile("result.csv");
    resultFile << "Distance(m),Speed(m/s),BrakingDistance(m),Result\n";  

    int successCount = 0;
    int failCount = 0;

    for (int i = 0; i < testCount; ++i) {
        float distance = randomFloat(0.5, 8.0);   // 거리: 0.5m ~ 8.0m
        float speed = randomFloat(0.5, MAX_SPEED); // 속도: 0.5m/s ~ 5.56m/s 제한
        float ttc = getTTC(distance, speed);
        float brakingDistance = BrakingDistance(speed);
        State state = updateState(distance, speed, ttc);

        cout << fixed << setprecision(2);
        cout << "\n[Test #" << (i+1) << "]" << endl;
        cout << "거리: " << distance << "m, 속도: " << speed << "m/s" << endl;
        cout << "TTC: " << ttc << "초 → 상태: " << stateToString(state) << endl;
        cout << "필요 제동 거리: " << brakingDistance << "m" << endl;

        if (brakingDistance <= distance) {
            cout << "감속 성공" << endl;
            successCount++;
            resultFile  << distance << "," << speed << "," << brakingDistance << ",Success\n";
        } 
        else {
            cout << "감속 실패" << endl;
            failCount++;
            resultFile << distance << "," << speed << "," << brakingDistance << ",Fail\n";
        }
    }

    // 전체 통계
    cout << "\n=== 통계 결과 ===" << endl;
    cout << "성공: " << successCount << "회" << endl;
    cout << "실패: " << failCount << "회" << endl;

    resultFile.close();

    return 0;
}