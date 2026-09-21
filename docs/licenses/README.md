# Лицензии ML-кандидатов

В production lock закреплены CatBoost 1.2.10 (Apache-2.0) и LightGBM 4.7.0
(MIT). Полные тексты с copyright notices сохранены рядом без изменения из
тегов поставщиков:

- [CatBoost v1.2.10](https://github.com/catboost/catboost/blob/v1.2.10/LICENSE)
- [LightGBM v4.7.0](https://github.com/microsoft/LightGBM/blob/v4.7.0/LICENSE)

Python distributions устанавливаются целиком с их собственными license files;
эти локальные копии не заменяют уведомления о транзитивных зависимостях.
Параметры CatBoost запрещают запись служебных файлов и построение графиков.
Optional plotting API и сетевые интеграции в обучающем контуре не вызываются.
