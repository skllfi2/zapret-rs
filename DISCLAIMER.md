# Юридическая информация и отказ от ответственности / Legal Disclaimer

## 🇷🇺 Русский (Russian)

### 1. Назначение программного обеспечения
Программное обеспечение **zapret-rs** разработано исключительно в **образовательных, исследовательских целях и для проведения сетевой диагностики**. Основная функциональность проекта направлена на:
* Исследование поведения сетевых стеков TCP/IP и UDP в различных сетевых топологиях.
* Диагностику задержек, деградации трафика, фрагментации пакетов и некорректной обработки TCP Window / Window Scaling сетевым оборудованием.
* Анализ работы сетевых драйверов пакетной фильтрации на базе технологии WinDivert в среде ОС Windows.
* Настройку безопасных защищенных протоколов разрешения доменных имен DNS over HTTPS (DoH) для предотвращения атак типа Man-in-the-Middle (MitM) и спуфинга DNS.

### 2. Соблюдение законодательства Российской Федерации
* Данное программное обеспечение **не предназначено и не должно использоваться** для получения доступа к информации, ресурсам или сервисам, доступ к которым ограничен или запрещен на территории Российской Федерации в соответствии с Федеральным законом от 27.07.2006 № 149-ФЗ «Об информации, информационных технологиях и о защите информации» и иными нормативно-правовыми актами РФ.
* Разработчики проекта не поддерживают, не поощряют и прямо осуждают неправомерное использование ПО для доступа к экстремистским материалам, материалам, нарушающим законные права граждан, а также ресурсам, включенным в Единый реестр запрещенных сайтов (ЕАИС Роскомнадзора).
* Настоящий репозиторий и связанная документация не содержат призывов, рекламы или инструкций по обходу установленных законодательством блокировок (в соответствии с критериями Приказа Роскомнадзора № 168).

### 3. Ответственность пользователя
* Вся ответственность за конфигурирование, используемые списки сетевых адресов (`lists/`), передаваемые аргументы и последствия запуска программного обеспечения в полном объеме возлагается на конечного пользователя.
* Конечный пользователь обязан самостоятельно удостовериться, что конфигурация программного обеспечения и посещаемые сетевые ресурсы соответствуют действующему законодательству юрисдикции, в которой оно запускается.

### 4. Отказ от гарантий (AS IS)
Программное обеспечение предоставляется на условиях лицензии MIT «КАК ЕСТЬ» («AS IS»), без каких-либо явных или подразумеваемых гарантий пригодности для конкретных целей. Авторы и контрибьюторы проекта не несут ответственности за любые прямые или косвенные убытки, сбои операционной системы, прерывания связи или правовые последствия, возникшие в результате применения данного ПО.

---

## 🇬🇧 English

### 1. Purpose of the Software
The **zapret-rs** software is developed strictly for **educational, research, and network diagnostic purposes**. The project focuses on:
* Researching TCP/IP and UDP network stack behaviors across varied network topologies.
* Analyzing latency, packet fragmentation, and window scaling anomalies across middleboxes.
* Diagnosing Windows packet filtering mechanisms via the WinDivert kernel engine.
* Configuring secure DNS over HTTPS (DoH) protocols to safeguard against DNS spoofing and eavesdropping.

### 2. Regulatory Compliance
* This software is **not intended and must not be used** to circumvent lawful access restrictions, copyright protections, or access content prohibited under applicable laws and regulations in any jurisdiction, including Federal Law No. 149-FZ of the Russian Federation.
* The authors neither promote nor endorse any unlawful use of network analysis tools.

### 3. User Responsibility
* The end user bears full and sole responsibility for ensuring that their use of this software, including target addresses and execution parameters, strictly complies with all local, national, and international laws.

### 4. Disclaimer of Warranty
This software is provided "AS IS", without warranty of any kind, express or implied. In no event shall the authors or copyright holders be liable for any claim, damages, or other liability arising from the use of this software.
