#include stdio.h

float getTTC(float distance, float velocity) {
    float ttc = 0.0;
    ttc = distance / velocity;

    return ttc
}

enum State {
    SAFE,
    WARNING,
    DECELERATE
};

State currentState = SAFE;

void updateState(float ttc) {
    if (ttc >= 2.0) {
        currentState = SAFE;
    }
    else if (ttc >= 1.2) {
        currentState = WARNING;
    }
    else {
        currentState = DECELERATE;
    }
}


void loop() {
    float distance = readLidar();
    float velocity = readVelocity();
    float ttc = getTTC(distance, velocity);

    updateState(ttc);

    switch (currentState) {
        case SAFE:
            break;
        case WARNING:
            break;
        case DECELERATE:
            break;
    }

    delay(20);
}