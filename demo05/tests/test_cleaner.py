from app.services.data_cleaner import RentDataCleaner


def test_cleaner_normalizes_price_area_and_house_type():
    cleaner = RentDataCleaner()
    result = cleaner.clean_record(
        {
            "source": "test",
            "district": " 朝阳区 ",
            "community": "望京西园",
            "rent_price": "0.68万/月",
            "area": "62㎡",
            "house_type": "二室一厅",
            "orientation": "朝南",
            "floor": "中楼层/18层",
            "tags": "近地铁,整租",
        }
    )

    assert result["rent_price"] == 6800
    assert result["area"] == 62
    assert result["house_type"] == "2室1厅"
    assert result["orientation"] == "南"
    assert result["unit_price"] == 109.68


def test_cleaner_drops_unreasonable_rows():
    cleaner = RentDataCleaner()
    result = cleaner.clean_record(
        {
            "district": "朝阳区",
            "community": "异常小区",
            "rent_price": "999999元/月",
            "area": "10㎡",
            "house_type": "1室1厅",
        }
    )

    assert result is None
