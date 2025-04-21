#include stdio.h

int main(void) {
    float velocity = 0.0;
    float distance = 0.0;
    float ttc = 0.0;
}

void loop() {
    float distance = readLidar();
    float velocity = readVelocity();

    if (velocity > 0) {
        float ttc = distance / velocity;
        if (ttc <= 1.2) {
            //진동 or led로 경고 출력
            // 서보모터 감속 시작
        }
    }

    delay(20);
}