import os
import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg') #TkinterとMatplotlibの競合回避のためにMatplotlibの非GUIバックエンドの使用
import matplotlib.pyplot as plt
import japanize_matplotlib # 日本語を画像タイトルに表示するために必要
import urllib.parse
import ssl
from datetime import datetime, timedelta
from json2polygon import get_coordinates_from_uuid




def save_ndvi_image_from_uuid(polygon_uuid='29996564-6256-402b-b48b-5daafda706f5', date_start_str='2023-07-21'):
    
    
    # SSL証明書の検証を無視する設定（セキュリティ上のリスクがあるため注意が必要です）
    ssl._create_default_https_context = ssl._create_unverified_context


    # Sentinel Hubからのデータ取得に関する設定
    from sentinelhub import (
        SHConfig,
        DataCollection,
        SentinelHubCatalog,
        SentinelHubRequest,
        SentinelHubStatistical,
        BBox,
        bbox_to_dimensions,
        CRS,
        MimeType,
        Geometry,
    )

    # Sentinel Hubへの認証情報
    ID = 'sh-a8ab20d0-6718-434f-bb63-1db6081c4ef5'
    OAuth = 'PtXBcCDFSzyh04Bmc0gHMD7SyMj9nODN'


    config = SHConfig()
    config.sh_client_id = ID
    config.sh_client_secret = OAuth
    config.sh_token_url = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
    config.sh_base_url = "https://sh.dataspace.copernicus.eu"
    config.save("cdse")

    # JSONファイルが保存されているフォルダのパス
    json_folder_path = 'JSON'  

    # 指定されたフォルダ内のすべてのJSONファイルを処理
    aoi_coords_wgs84 = None
    for filename in os.listdir(json_folder_path):
        if aoi_coords_wgs84 == None:
            if filename.endswith('.json'):
                file_path = os.path.join(json_folder_path, filename)    
                aoi_coords_wgs84 = get_coordinates_from_uuid(file_path, polygon_uuid) # polygon_uuidが一致したら座標をえる


    # 緯度と経度のリストを生成
    lons = [coord[0] for coord in aoi_coords_wgs84[0]]
    lats = [coord[1] for coord in aoi_coords_wgs84[0]]

    # 最小値と最大値を見つける
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)

    # 結果を格納
    aoi_coords_wgs84 = [[min_lon, min_lat], [max_lon, max_lat]]




    # 解像度とバウンディングボックスの設定
    resolution = 10
    aoi_bbox = BBox(bbox=aoi_coords_wgs84, crs=CRS.WGS84)
    aoi_size = bbox_to_dimensions(aoi_bbox, resolution=resolution)

    #Stringからdatetimeに変換
    date_start = datetime.strptime(date_start_str, '%Y-%m-%d')

    #衛星は5日間隔で飛ぶため最低1枚の画像を取得するために5日足す
    date_end = date_start + timedelta(days=5)

    #stringに変換しなおす
    date_end_str = date_end.strftime('%Y-%m-%d')

    # 時間範囲とバウンディングボックスで衛星画像を検索
    time_interval = date_start, date_end_str

    catalog = SentinelHubCatalog(config=config)
    search_iterator = catalog.search(
        DataCollection.SENTINEL2_L2A,
        bbox=aoi_bbox,
        time=time_interval,
        fields={"include": ["id", "properties.datetime"], "exclude": []},
    )

    results = list(search_iterator)
    print("Total number of results:", len(results))

    for result in results:
        print(result)
    temp_str = results[0]['properties']['datetime']
    taken_date = temp_str.split('T')[0]

    #True color取得
    evalscript_true_color = """
        //VERSION=3

        function setup() {
            return {
                input: [{
                    bands: ["B02", "B03", "B04"]
                }],
                output: {
                    bands: 3
                }
            };
        }

        function evaluatePixel(sample) {
            return [sample.B04, sample.B03, sample.B02];
        }
    """

    request_true_color = SentinelHubRequest(
        evalscript=evalscript_true_color,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A.define_from(
                    name="s2l2a", service_url="https://sh.dataspace.copernicus.eu"
                ),
                time_interval=time_interval,
                other_args={"dataFilter": {"mosaickingOrder": "leastCC"}},
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.PNG)],
        bbox=aoi_bbox,
        size=aoi_size,
        config=config,
    )
    true_color_imgs = request_true_color.get_data()
    true_image = true_color_imgs[0]
    print(f"Image type: {true_image.dtype}")

    

    # NDVI画像取得用のEvalscript
    evalscript_ndvi = """
    //VERSION=3
    function setup() {
    return {
        input: [{
        bands: [
            "B04",
            "B08",
            "dataMask"
        ]
        }],
        output: {
        bands: 1 // 出力を1バンドに変更
        }
    }
    }

    function evaluatePixel(sample) {
        let val = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
        
        // NDVI値を0から1の範囲に正規化
        let normalizedVal = (val + 1) / 2; 
        
        // dataMaskを考慮してNDVI値を返す
        return [val * sample.dataMask];
    }

    """
    # NDVI画像のリクエストと表示
    request_ndvi_img = SentinelHubRequest(
        evalscript=evalscript_ndvi,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L2A.define_from(
                    name="s2l2a", service_url="https://sh.dataspace.copernicus.eu"
                ),
                time_interval=time_interval,
                other_args={"dataFilter": {"mosaickingOrder": "leastCC"}},
            )
        ],
        responses=[SentinelHubRequest.output_response("default", MimeType.PNG)],
        bbox=aoi_bbox,
        size=aoi_size,
        config=config,
    )

    ndvi_img = request_ndvi_img.get_data()

    print(
        f"Returned data is of type = {type(ndvi_img)} and length {len(ndvi_img)}."
    )
    print(
        f"Single element in the list is of type {type(ndvi_img[-1])} and has shape {ndvi_img[-1].shape}"
    )

    # ndvi_img[0]からndviデータを取得
    ndvi = ndvi_img[0]
    print(f"Image type: {ndvi.dtype}")

    # Matplotlibのsubplotを使用して、TrueColorとNDVIを並べて表示
    fig, axs = plt.subplots(1,2, figsize = (12, 6))

    # Matplotlibを使用してTrueColor画像を表示
    axs[0].imshow(true_image)
    axs[0].axis('off')

    # Matplotlibを使用してカラーマップを適用
    ndvi_im = axs[1].imshow(ndvi, cmap='coolwarm')
    fig.colorbar(ndvi_im, ax=axs[1])  # カラーバーを表示
    plt.axis('off')  # 軸を非表示にする

    # 全体のタイトルを設定
    plt.suptitle('Photo taken: ' + polygon_uuid + ' @ '+ taken_date)

    # サブプロット間と周辺の余白を調整
    fig.subplots_adjust(left=0.05, wspace=0.3)


    # 画像として保存
    image_path = 'templates/image/temporary/ndvi_image.png'
    plt.savefig(image_path, bbox_inches='tight', pad_inches=0)
    plt.close()  # プロットをクローズ

    return image_path
