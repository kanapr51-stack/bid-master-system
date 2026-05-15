# Bid Master System — Dashboard
> อัปเดตอัตโนมัติโดย Obsidian Dataview | ดูแลโดย Natalia

---

## งานที่กำลังทำอยู่

```tasks
not done
path includes Agent/about work/work_overview
```

---

## ไอเดียที่ยังค้างอยู่

```tasks
not done
path includes ideas/future_development
```

---

## สถานะ Sub Agent

```dataview
TABLE role AS "บทบาท", expertise AS "ความเชี่ยวชาญ", status AS "สถานะ"
FROM "Agent"
WHERE file.name != "README" AND file.name != "profile"
SORT name ASC
```

---

## ไฟล์ที่แก้ไขล่าสุด

```dataview
TABLE file.mtime AS "แก้ไขล่าสุด"
WHERE file.name != "Dashboard"
SORT file.mtime DESC
LIMIT 10
```

---

## Backup ล่าสุด

```dataview
LIST
FROM "backups"
SORT file.mtime DESC
LIMIT 5
```
