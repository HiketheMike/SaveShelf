# SaveShelf

Ứng dụng web (Python/Flask) thông báo cho người mua gần đó biết cửa hàng nào đang giảm giá thực phẩm cận date.

## Chạy
```bash
pip install -r requirements.txt
python app.py          # mở http://127.0.0.1:5000
```
Lần chạy đầu tự tạo `saveshelf.db` với dữ liệu mẫu quanh Quận 1, TP.HCM.
Tài khoản cửa hàng demo: `hoasua@demo.vn` / `123456`.

## Cách hoạt động
- **Người mua**: cho phép định vị (hoặc bấm bản đồ), chọn bán kính, xem ưu đãi sắp xếp theo khoảng cách / mức giảm / hạn dùng. Bật thông báo để nhận tin ngay khi có món mới (trang kiểm tra mỗi 30 giây, dùng Notification API của trình duyệt).
- **Cửa hàng**: đăng ký (ghim vị trí trên bản đồ), đăng sản phẩm còn ≤ 7 ngày hạn, giảm tối thiểu 10%. Hệ thống gợi ý mức giảm: 1 ngày → 50%, ≤ 3 ngày → 30%, còn lại → 20%.
- API: `GET /api/deals?lat=&lng=&radius=&days=&category=&sort=`

## Biến môi trường
`SECRET_KEY` (bắt buộc đổi khi triển khai), `SAVESHELF_DB`, `PORT`, `DEBUG`.
