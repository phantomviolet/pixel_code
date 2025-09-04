package com.example.temp2_kickboard

import android.Manifest // 위치 권한
import android.annotation.SuppressLint
import android.content.Context
import android.content.pm.PackageManager
import android.widget.LinearLayout
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.getValue // by 키워드 사용을 위해 추가
import androidx.compose.runtime.setValue // by 키워드 사용을 위해 추가
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat // 권한 확인
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.google.android.gms.location.FusedLocationProviderClient // 위치 서비스
import com.google.android.gms.location.LocationServices
import com.skt.Tmap.TMapMarkerItem // TMap 마커
import com.skt.Tmap.TMapPoint // TMap 좌표
import com.skt.Tmap.TMapView
import com.example.temp2_kickboard.ui.theme.Temp2_kickboardTheme
import kotlinx.coroutines.launch // rememberCoroutineScope와 함께 사용
import kotlin.io.path.name

// import android.graphics.BitmapFactory // 커스텀 마커 아이콘 사용 시
// import com.example.temp2_kickboard.R // 커스텀 마커 아이콘 사용 시

// --- TMapViewContainer 클래스 ---
class TMapViewContainer(val context: Context) {
    val tMapView: TMapView = TMapView(context).apply {
        setSKTMapApiKey("4Gqu3WNznX1o60OkPK5Lo360oUutv4NNaVOWX1Xb") // TODO: 실제 유효한 API 키로!
        // TODO: 지도 초기 줌 레벨, 중심점 등 설정
    }

    fun onResume() { /* TODO: SDK 문서 참고 */ }
    fun onPause() { /* TODO: SDK 문서 참고 */ }
    fun onDestroy() { /* TODO: SDK 문서 참고, 리소스 해제 */ }

    fun addMarkerAtLocation(latitude: Double, longitude: Double, markerId: String = "currentLocation", markerName: String = "현재 위치") {
        val markerItem = TMapMarkerItem()
        val tMapPoint = TMapPoint(latitude, longitude)
        markerItem.tMapPoint = tMapPoint
        markerItem.id = markerId
        markerItem.name = markerName
        markerItem.canShowCallout = true
        tMapView.removeMarkerItem(markerId)
        tMapView.addMarkerItem(markerId, markerItem)
        tMapView.setCenterPoint(longitude, latitude)
        tMapView.zoomLevel = 17
    }
}

// --- MapScreen Composable 함수 ---
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapScreen() {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val tmapViewContainer = remember { TMapViewContainer(context) }
    val fusedLocationClient = remember { LocationServices.getFusedLocationProviderClient(context) }
    var userDeniedPermissionInitially by remember { mutableStateOf(false) }

    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    val moveToCurrentLocation = {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            getCurrentDeviceLocation(fusedLocationClient) { lat, lon ->
                tmapViewContainer.addMarkerAtLocation(lat, lon, markerName = "현재 GPS 위치")
                scope.launch {
                    snackbarHostState.showSnackbar("현재 위치로 이동했습니다.")
                }
            }
        } else {
            scope.launch {
                snackbarHostState.showSnackbar("현재 위치로 이동하려면 위치 권한이 필요합니다.")
            }
            // 권한이 없다면 다시 요청할 수도 있음
            // locationPermissionLauncher.launch(...)
        }
    }

    val locationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val fineLocationGranted = permissions.getOrDefault(Manifest.permission.ACCESS_FINE_LOCATION, false)
        val coarseLocationGranted = permissions.getOrDefault(Manifest.permission.ACCESS_COARSE_LOCATION, false)

        if (fineLocationGranted || coarseLocationGranted) {
            moveToCurrentLocation()
        } else {
            userDeniedPermissionInitially = true
            scope.launch {
                snackbarHostState.showSnackbar("위치 권한이 거부되어 현재 위치를 표시할 수 없습니다. 앱 설정에서 권한을 허용해주세요.")
            }
        }
    }

    LaunchedEffect(Unit) {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            moveToCurrentLocation() // 앱 시작 시 현재 위치로 이동
        } else {
            locationPermissionLauncher.launch(
                arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION)
            )
        }
    }

    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_RESUME -> tmapViewContainer.onResume()
                Lifecycle.Event.ON_PAUSE -> tmapViewContainer.onPause()
                Lifecycle.Event.ON_DESTROY -> tmapViewContainer.onDestroy()
                else -> { /* 다른 생명주기 이벤트 처리 */ }
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose {
            lifecycleOwner.lifecycle.removeObserver(observer)
        }
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            Column(modifier = Modifier.background(MaterialTheme.colorScheme.primaryContainer)) {
                SearchLocationBar(
                    hintText = "장소, 버스, 지하철 검색",
                    onSearchClick = { /* TODO: 검색 로직 */ }
                )
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    RouteLocationBar(
                        modifier = Modifier.weight(1f),
                        prefix = "출발:",
                        locationText = "현재 위치 또는 출발지",
                        onClick = { /* TODO: 출발지 선택 */ }
                    )
                    RouteLocationBar(
                        modifier = Modifier.weight(1f),
                        prefix = "도착:",
                        locationText = "도착지 선택",
                        onClick = { /* TODO: 도착지 선택 */ }
                    )
                }
            }
        },
        bottomBar = {
            MapBottomNavigationBar()
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { moveToCurrentLocation() }
            ) {
                Icon(Icons.Filled.MyLocation, "현재 위치로 이동")
            }
        }
    ) { innerPadding ->
        Box(modifier = Modifier
            .padding(innerPadding)
            .fillMaxSize()) {
            AndroidView(
                factory = { tmapViewContainer.tMapView },
                modifier = Modifier.fillMaxSize()
            )

            if (userDeniedPermissionInitially &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED &&
                ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp), // innerPadding을 여기서도 적용할지 고려
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        "지도를 사용하려면 위치 권한이 필요합니다. 앱 설정에서 권한을 허용해주세요.",
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.error // 눈에 띄게 에러 색상 사용 가능
                    )
                }
            }
        }
    }
}

// 현재 장치 위치를 가져오는 함수
@SuppressLint("MissingPermission")
fun getCurrentDeviceLocation(
    fusedLocationClient: FusedLocationProviderClient,
    onLocationFetched: (latitude: Double, longitude: Double) -> Unit
) {
    fusedLocationClient.lastLocation
        .addOnSuccessListener { location ->
            if (location != null) {
                onLocationFetched(location.latitude, location.longitude)
            } else {
                println("마지막 위치 정보를 가져올 수 없습니다. 새 위치를 요청하거나 GPS를 확인하세요.")
                // TODO: 사용자에게 알림 (예: Toast, SnackBar)
                // onLocationFetched(37.5665, 126.9780) // 예: 서울 시청으로 기본값
            }
        }
        .addOnFailureListener { e ->
            println("위치 정보 가져오기 실패: ${e.message}")
            // TODO: 에러 처리 및 사용자 알림
        }
}


// --- 상단 바 관련 Composable 함수들 (구현 포함) ---
@Composable
fun SearchLocationBar(hintText: String, onSearchClick: () -> Unit) {
    Surface(
        onClick = onSearchClick,
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 12.dp),
        shape = RoundedCornerShape(24.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 4.dp
    ) {
        Row(
            modifier = Modifier
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                imageVector = Icons.Filled.Search,
                contentDescription = "검색 아이콘",
                tint = MaterialTheme.colorScheme.onSurfaceVariant
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = hintText,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 16.sp
            )
        }
    }
}

@Composable
fun RouteLocationBar(
    modifier: Modifier = Modifier,
    prefix: String,
    locationText: String,
    onClick: () -> Unit
) {
    Surface(
        onClick = onClick,
        modifier = modifier
            .height(48.dp),
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 2.dp
    ) {
        Row(
            modifier = Modifier
                .fillMaxHeight()
                .padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = prefix,
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(end = 4.dp)
            )
            Text(
                text = locationText,
                fontSize = 14.sp,
                color = MaterialTheme.colorScheme.onSurface,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

// --- 하단 바 관련 Composable 함수들 (구현 포함) ---
@Composable
fun MapBottomNavigationBar() {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shadowElevation = 8.dp
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(MaterialTheme.colorScheme.surface)
                .padding(vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceAround,
            verticalAlignment = Alignment.CenterVertically
        ) {
            CircleButton(icon = Icons.Filled.LocationOn, contentDescription = "지도") { /* 지도 관련 동작 */ }
            CircleButton(icon = Icons.Filled.Home, contentDescription = "홈") { /* 홈 화면 이동 */ }
            CircleButton(icon = Icons.Filled.Settings, contentDescription = "설정") { /* 설정 화면 이동 */ }
            CircleButton(icon = Icons.Filled.Person, contentDescription = "내 정보") { /* 내 정보 화면 이동 */ }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CircleButton(icon: ImageVector, contentDescription: String, onClick: () -> Unit) {
    IconButton(
        onClick = onClick,
        modifier = Modifier
            .size(56.dp)
            .clip(CircleShape)
    ) {
        Icon(
            imageVector = icon,
            contentDescription = contentDescription,
            tint = MaterialTheme.colorScheme.primary
        )
    }
}

// --- Preview 함수 ---
@Preview(showBackground = true)
@Composable
fun MapScreenPreview() {
    Temp2_kickboardTheme {
        Scaffold( // FAB와 전체 레이아웃을 미리보기 위해 Scaffold 사용
            topBar = {
                Column(modifier = Modifier.background(MaterialTheme.colorScheme.primaryContainer)) {
                    SearchLocationBar(hintText = "검색", onSearchClick = {})
                    Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), Arrangement.spacedBy(8.dp)) {
                        RouteLocationBar(Modifier.weight(1f), "출발:", "출발지", {})
                        RouteLocationBar(Modifier.weight(1f), "도착:", "도착지", {})
                    }
                }
            },
            bottomBar = { MapBottomNavigationBar() },
            floatingActionButton = {
                FloatingActionButton(onClick = { }) {
                    Icon(Icons.Filled.MyLocation, "현재 위치로 이동")
                }
            }
        ) { paddingValues ->
            Box(
                modifier = Modifier
                    .padding(paddingValues)
                    .fillMaxSize(),
                contentAlignment = Alignment.Center
            ) {
                Text("지도 영역 (실제 지도는 실행 시 확인)")
            }
        }
    }
}




