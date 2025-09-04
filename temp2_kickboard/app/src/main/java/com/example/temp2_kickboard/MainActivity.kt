package com.example.temp2_kickboard

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.* // remember, mutableStateOf, by 추가
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import com.example.temp2_kickboard.ui.theme.Temp2_kickboardTheme
// import com.example.temp2_kickboard.R // R은 이미 이 패키지에 있으므로 명시적 import 불필요할 수 있음
// import com.example.temp2_kickboard.MapScreen // MapScreen을 사용하므로 import 추가 (MapScreen.kt가 같은 패키지에 있다면 생략 가능)

// 현재 보여줄 화면을 나타내는 Enum (파일 상단이나 MainActivity 클래스 바깥에 정의)
enum class Screen {
    Welcome,
    Map
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)

        setContent {
            Temp2_kickboardTheme {
                // 현재 화면 상태를 기억하는 변수, 초기 화면은 Welcome
                var currentScreen by remember { mutableStateOf(Screen.Welcome) }

                // 현재 화면 상태에 따라 다른 Composable 함수를 호출
                when (currentScreen) {
                    Screen.Welcome -> {
                        WelcomeScreen(
                            onNavigateToMap = {
                                currentScreen = Screen.Map // 상태를 Map으로 변경하여 화면 전환
                            }
                        )
                    }
                    Screen.Map -> {
                        MapScreen() // MapScreen Composable 호출
                        // MapScreen.kt가 이 파일과 다른 패키지에 있다면,
                        // MapScreen()을 호출하기 위해 해당 파일/클래스를 import 해야 합니다.
                        // 예: import com.example.temp2_kickboard.ui.map.MapScreen
                    }
                }
            }
        }
    }
}

// WelcomeScreen Composable 함수: 화면 전환 콜백(onNavigateToMap)을 파라미터로 받도록 수정
@Composable
fun WelcomeScreen(onNavigateToMap: () -> Unit) { // 콜백 함수 파라미터 추가
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(16.dp),
            verticalArrangement = Arrangement.SpaceBetween,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Spacer(modifier = Modifier.weight(1f))

            Image(
                painter = painterResource(id = R.drawable.temp_logo),
                contentDescription = "App Logo",
                modifier = Modifier.size(150.dp)
            )

            Spacer(modifier = Modifier.weight(1f))

            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                ActionButton(text = "Sign up") {
                    println("Sign up 버튼 클릭됨")
                    // 필요에 따라 Sign up 후 Map으로 이동하거나 다른 로직 수행
                    onNavigateToMap() // MapScreen으로 이동
                }
                ActionButton(text = "Sign in") {
                    println("Sign in 버튼 클릭됨")
                    onNavigateToMap() // MapScreen으로 이동
                }
            }
            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
fun ActionButton(text: String, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .height(50.dp)
    ) {
        Text(text)
    }
}

@Preview(showBackground = true, widthDp = 320, heightDp = 640)
@Composable
fun WelcomeScreenPreview() {
    Temp2_kickboardTheme {
        // Preview에서는 실제 화면 전환 로직이 필요 없으므로 빈 람다를 전달
        WelcomeScreen(onNavigateToMap = {})
    }
}

