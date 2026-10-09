#!/usr/bin/env python3
"""Generate src/letsbot_connector/i18n/{ar,es,pt}.po from the exported .pot.

Re-export the template after changing strings (see README.md), then run:
    python3 scripts/make_po.py && python3 build.py
Arabic is Modern Standard Arabic.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
I18N = os.path.join(HERE, "..", "src", "letsbot_connector", "i18n")
LANGS = {"ar": ("Arabic", 1), "es": ("Spanish", 2), "pt": ("Portuguese", 3)}

# (msgid, ar, es, pt)
TRANSLATIONS = [
    ('<span class="o_form_label">Last contact: </span>', '<span class="o_form_label">آخر اتصال: </span>', '<span class="o_form_label">Último contacto: </span>', '<span class="o_form_label">Último contato: </span>'),
    ('<span class="o_form_label">Workspace: </span>', '<span class="o_form_label">مساحة العمل: </span>', '<span class="o_form_label">Espacio de trabajo: </span>', '<span class="o_form_label">Espaço de trabalho: </span>'),
    ('<span class="o_stat_text">WhatsApp</span>\n                        <span class="o_stat_text">(LetsBot)</span>', '<span class="o_stat_text">واتساب</span>\n                        <span class="o_stat_text">(LetsBot)</span>', '<span class="o_stat_text">WhatsApp</span>\n                        <span class="o_stat_text">(LetsBot)</span>', '<span class="o_stat_text">WhatsApp</span>\n                        <span class="o_stat_text">(LetsBot)</span>'),
    ('<span> pending webhook events</span>', '<span> حدث webhook في الانتظار</span>', '<span> eventos de webhook pendientes</span>', '<span> eventos de webhook pendentes</span>'),
    ('API Key Validity (days)', 'مدة صلاحية مفتاح API (بالأيام)', 'Validez de la clave API (días)', 'Validade da chave de API (dias)'),
    ('Advanced', 'إعدادات متقدمة', 'Avanzado', 'Avançado'),
    ('Attempts', 'المحاولات', 'Intentos', 'Tentativas'),
    ('CRM Leads', 'العملاء المحتملون (CRM)', 'Oportunidades CRM', 'Leads do CRM'),
    ('Company', 'الشركة', 'Compañía', 'Empresa'),
    ('Config Settings', 'إعدادات التهيئة', 'Ajustes de configuración', 'Definições de configuração'),
    ('Connect LetsBot first.', 'اربط LetsBot أولًا.', 'Conecte LetsBot primero.', 'Conecte o LetsBot primeiro.'),
    ('Connect to LetsBot', 'الربط مع LetsBot', 'Conectar con LetsBot', 'Conectar ao LetsBot'),
    ('Connected', 'متصل', 'Conectado', 'Conectado'),
    ('Connection', 'الاتصال', 'Conexión', 'Conexão'),
    ('Contact', 'جهة الاتصال', 'Contacto', 'Contato'),
    ("Could not reach LetsBot. Check the server's internet access and try again.", 'تعذّر الوصول إلى LetsBot. تحقّق من اتصال الخادم بالإنترنت ثم حاول مرة أخرى.', 'No se pudo contactar con LetsBot. Compruebe el acceso a Internet del servidor e inténtelo de nuevo.', 'Não foi possível contatar o LetsBot. Verifique o acesso à internet do servidor e tente novamente.'),
    ('Created by', 'أنشئ بواسطة', 'Creado por', 'Criado por'),
    ('Created on', 'أنشئ في', 'Creado el', 'Criado em'),
    ('Customer Invoices', 'فواتير العملاء', 'Facturas de cliente', 'Faturas de clientes'),
    ('Defaults work for most companies.', 'الإعدادات الافتراضية مناسبة لمعظم الشركات.', 'Los valores predeterminados sirven para la mayoría de las empresas.', 'Os valores padrão servem para a maioria das empresas.'),
    ('Deliveries', 'عمليات التسليم', 'Entregas', 'Entregas'),
    ('Delivery ID', 'معرّف الإرسال', 'ID de entrega', 'ID de entrega'),
    ('Disconnect', 'قطع الاتصال', 'Desconectar', 'Desconectar'),
    ('Disconnect LetsBot? The LetsBot API key will be revoked and webhooks stop immediately.', 'هل تريد قطع الاتصال بـ LetsBot؟ سيُلغى مفتاح API الخاص بـ LetsBot وتتوقف إشعارات webhook فورًا.', '¿Desconectar LetsBot? La clave API de LetsBot se revocará y los webhooks se detendrán de inmediato.', 'Desconectar o LetsBot? A chave de API do LetsBot será revogada e os webhooks param imediatamente.'),
    ('Disconnected by LetsBot', 'قُطع الاتصال من جهة LetsBot', 'Desconectado por LetsBot', 'Desconectado pelo LetsBot'),
    ('Display Name', 'الاسم المعروض', 'Nombre mostrado', 'Nome de exibição'),
    ('Email Thread', 'سلسلة البريد الإلكتروني', 'Hilo de correo electrónico', 'Thread de e-mail'),
    ('Event', 'الحدث', 'Evento', 'Evento'),
    ('Failed', 'فشل', 'Fallido', 'Falhou'),
    ('ID', 'المعرّف', 'ID', 'ID'),
    ('Integration User', 'مستخدم التكامل', 'Usuario de integración', 'Usuário de integração'),
    ('Invalid URL from LetsBot: %s', 'رابط غير صالح من LetsBot: %s', 'URL no válida de LetsBot: %s', 'URL inválida do LetsBot: %s'),
    ('Invalid pairing state.', 'حالة الربط غير صالحة.', 'Estado de vinculación no válido.', 'Estado de pareamento inválido.'),
    ('Last Contact', 'آخر اتصال', 'Último contacto', 'Último contato'),
    ('Last Error', 'آخر خطأ', 'Último error', 'Último erro'),
    ('Last HTTP Status', 'آخر حالة HTTP', 'Último estado HTTP', 'Último status HTTP'),
    ('Last Updated by', 'آخر تحديث بواسطة', 'Última actualización por', 'Última atualização por'),
    ('Last Updated on', 'آخر تحديث في', 'Última actualización el', 'Última atualização em'),
    ('LetsBot', 'LetsBot', 'LetsBot', 'LetsBot'),
    ('LetsBot Connect URL', 'رابط الربط مع LetsBot', 'URL de conexión de LetsBot', 'URL de conexão do LetsBot'),
    ('LetsBot Pairing Service', 'خدمة الربط مع LetsBot', 'Servicio de vinculación de LetsBot', 'Serviço de pareamento do LetsBot'),
    ('LetsBot Status', 'حالة LetsBot', 'Estado de LetsBot', 'Status do LetsBot'),
    ('LetsBot Webhook Event', 'حدث webhook من LetsBot', 'Evento de webhook de LetsBot', 'Evento de webhook do LetsBot'),
    ('LetsBot Webhook Events', 'أحداث webhook من LetsBot', 'Eventos de webhook de LetsBot', 'Eventos de webhook do LetsBot'),
    ('LetsBot WhatsApp', 'واتساب LetsBot', 'LetsBot WhatsApp', 'LetsBot WhatsApp'),
    ('LetsBot Workspace', 'مساحة عمل LetsBot', 'Espacio de trabajo de LetsBot', 'Espaço de trabalho do LetsBot'),
    ('LetsBot did not accept the test event: %s', 'لم يقبل LetsBot الحدث التجريبي: %s', 'LetsBot no aceptó el evento de prueba: %s', 'O LetsBot não aceitou o evento de teste: %s'),
    ('LetsBot is notified (record id + status only) when these documents change, then re-reads them through the API.', 'يُرسَل إشعار إلى LetsBot (معرّف السجل وحالته فقط) عند تغيّر هذه المستندات، ثم يعيد قراءتها عبر واجهة API.', 'LetsBot recibe un aviso (solo el ID del registro y su estado) cuando cambian estos documentos y luego los vuelve a leer mediante la API.', 'O LetsBot é notificado (apenas ID do registro e status) quando esses documentos mudam e depois os relê pela API.'),
    ('LetsBot refused the connection request (HTTP %s).', 'رفض LetsBot طلب الاتصال (HTTP %s).', 'LetsBot rechazó la solicitud de conexión (HTTP %s).', 'O LetsBot recusou o pedido de conexão (HTTP %s).'),
    ('LetsBot returned a redirect to an unexpected domain.', 'أعاد LetsBot توجيهًا إلى نطاق غير متوقع.', 'LetsBot devolvió una redirección a un dominio inesperado.', 'O LetsBot retornou um redirecionamento para um domínio inesperado.'),
    ('LetsBot returned an invalid answer.', 'أعاد LetsBot ردًّا غير صالح.', 'LetsBot devolvió una respuesta no válida.', 'O LetsBot retornou uma resposta inválida.'),
    ('LetsBot: deliver webhook events', 'LetsBot: إرسال أحداث webhook', 'LetsBot: entregar eventos de webhook', 'LetsBot: entregar eventos de webhook'),
    ('Letsbot Chat Available', 'محادثة LetsBot متاحة', 'Chat de LetsBot disponible', 'Chat do LetsBot disponível'),
    ('Model', 'النموذج', 'Modelo', 'Modelo'),
    ('Next Attempt', 'المحاولة التالية', 'Próximo intento', 'Próxima tentativa'),
    ('No LetsBot conversation is available for this contact.', 'لا توجد محادثة LetsBot متاحة لجهة الاتصال هذه.', 'No hay ninguna conversación de LetsBot disponible para este contacto.', 'Não há conversa do LetsBot disponível para este contato.'),
    ('Not connected', 'غير متصل', 'No conectado', 'Não conectado'),
    ('Odoo 18+ only: the API key generated for LetsBot expires after this many days (1-365).', 'لـ Odoo 18 فأحدث فقط: تنتهي صلاحية مفتاح API المُنشأ لـ LetsBot بعد هذا العدد من الأيام (1-365).', 'Solo Odoo 18+: la clave API generada para LetsBot caduca tras este número de días (1-365).', 'Somente Odoo 18+: a chave de API gerada para o LetsBot expira após este número de dias (1-365).'),
    ('Only administrators can manage the LetsBot connection.', 'تقتصر إدارة الاتصال بـ LetsBot على المسؤولين.', 'Solo los administradores pueden gestionar la conexión con LetsBot.', 'Somente administradores podem gerenciar a conexão com o LetsBot.'),
    ('Only the LetsBot integration user can call this method.', 'لا يمكن استدعاء هذه الدالة إلا بواسطة مستخدم التكامل الخاص بـ LetsBot.', 'Solo el usuario de integración de LetsBot puede llamar a este método.', 'Somente o usuário de integração do LetsBot pode chamar este método.'),
    ('Pair this database with your LetsBot workspace. No API key to copy: Odoo hands a dedicated key to LetsBot securely.', 'اربط قاعدة البيانات هذه بمساحة عملك في LetsBot. لا حاجة إلى نسخ أي مفتاح API: يسلّم Odoo مفتاحًا مخصصًا إلى LetsBot بأمان.', 'Vincule esta base de datos con su espacio de trabajo de LetsBot. No hay que copiar ninguna clave API: Odoo entrega una clave dedicada a LetsBot de forma segura.', 'Vincule este banco de dados ao seu espaço de trabalho do LetsBot. Nenhuma chave de API para copiar: o Odoo entrega uma chave dedicada ao LetsBot com segurança.'),
    ('Pairing must be confirmed with the LetsBot integration key.', 'يجب تأكيد الربط باستخدام مفتاح التكامل الخاص بـ LetsBot.', 'La vinculación debe confirmarse con la clave de integración de LetsBot.', 'O pareamento deve ser confirmado com a chave de integração do LetsBot.'),
    ('Pending', 'قيد الانتظار', 'Pendiente', 'Pendente'),
    ('Pending Events', 'الأحداث قيد الانتظار', 'Eventos pendientes', 'Eventos pendentes'),
    ('Products', 'المنتجات', 'Productos', 'Produtos'),
    ('Real-time updates', 'التحديثات الفورية', 'Actualizaciones en tiempo real', 'Atualizações em tempo real'),
    ('Reconnect', 'إعادة الربط', 'Volver a conectar', 'Reconectar'),
    ('Record ID', 'معرّف السجل', 'ID del registro', 'ID do registro'),
    ('Record Last Update', 'آخر تحديث للسجل', 'Última actualización del registro', 'Última atualização do registro'),
    ('Retry', 'إعادة المحاولة', 'Reintentar', 'Tentar novamente'),
    ('Sales Orders', 'أوامر البيع', 'Pedidos de venta', 'Pedidos de venda'),
    ('Send test event', 'إرسال حدث تجريبي', 'Enviar evento de prueba', 'Enviar evento de teste'),
    ('Sent', 'أُرسل', 'Enviado', 'Enviado'),
    ('Sent At', 'وقت الإرسال', 'Enviado el', 'Enviado em'),
    ('State', 'الحالة', 'Estado', 'Estado'),
    ('State Values', 'قيم الحالة', 'Valores de estado', 'Valores de estado'),
    ('Test event delivered.', 'تم تسليم الحدث التجريبي.', 'Evento de prueba entregado.', 'Evento de teste entregue.'),
    ('The LetsBot connect URL is invalid: %s', 'رابط الربط مع LetsBot غير صالح: %s', 'La URL de conexión de LetsBot no es válida: %s', 'A URL de conexão do LetsBot é inválida: %s'),
    ('The pairing request has expired. Click Connect again in Odoo.', 'انتهت صلاحية طلب الربط. انقر على «الربط مع LetsBot» مرة أخرى في Odoo.', 'La solicitud de vinculación ha caducado. Vuelva a pulsar Conectar en Odoo.', 'O pedido de pareamento expirou. Clique em Conectar novamente no Odoo.'),
    ('The webhook secret must be at least 32 characters.', 'يجب ألا يقل سر webhook عن 32 حرفًا.', 'El secreto del webhook debe tener al menos 32 caracteres.', 'O segredo do webhook deve ter pelo menos 32 caracteres.'),
    ('This pairing request was replaced or already used.', 'تم استبدال طلب الربط هذا أو استخدامه من قبل.', 'Esta solicitud de vinculación fue reemplazada o ya se utilizó.', 'Este pedido de pareamento foi substituído ou já foi usado.'),
    ("User whose API key LetsBot uses. Leave empty to let the connector create a dedicated 'LetsBot Integration' user (recommended).", 'المستخدم الذي يستخدم LetsBot مفتاح API الخاص به. اتركه فارغًا ليُنشئ الموصل مستخدمًا مخصصًا باسم «LetsBot Integration» (موصى به).', "Usuario cuya clave API utiliza LetsBot. Déjelo vacío para que el conector cree un usuario dedicado 'LetsBot Integration' (recomendado).", "Usuário cuja chave de API o LetsBot utiliza. Deixe vazio para que o conector crie um usuário dedicado 'LetsBot Integration' (recomendado)."),
    ('Waiting for LetsBot', 'بانتظار LetsBot', 'Esperando a LetsBot', 'Aguardando o LetsBot'),
]


PLURAL = {"ar": "nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5;",
          "es": "nplurals=2; plural=(n != 1);", "pt": "nplurals=2; plural=(n != 1);"}


def po_quote(text):
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    lines = text.split("\n")
    if len(lines) == 1:
        return '"%s"' % lines[0]
    parts = ['""'] + ['"%s\\n"' % line for line in lines[:-1]] + ['"%s"' % lines[-1]]
    return "\n".join(parts)


def parse_msgid(block):
    out, active = None, False
    for line in block.splitlines():
        if line.startswith("msgid "):
            out, active = eval(line[6:]), True  # noqa: S307 - trusted local .pot string literal
        elif line.startswith("msgstr"):
            active = False
        elif active and line.startswith('"'):
            out += eval(line)  # noqa: S307
    return out


def main():
    with open(os.path.join(I18N, "letsbot_connector.pot"), encoding="utf-8") as fh:
        blocks = fh.read().strip().split("\n\n")
    table = {row[0]: row for row in TRANSLATIONS}
    for lang, (name, col) in LANGS.items():
        out = []
        for i, block in enumerate(blocks):
            msgid = parse_msgid(block)
            if i == 0:  # header
                header = block.replace('"Language-Team: \\n"\n', '"Language-Team: %s\\n"\n"Language: %s\\n"\n' % (name, lang))
                header = header.replace('"Plural-Forms: \\n"', '"Plural-Forms: %s\\n"' % PLURAL[lang])
                out.append(header.replace("# Translation of Odoo Server.", "# %s translation of letsbot_connector." % name))
                continue
            row = table.get(msgid)
            if row is None:
                raise SystemExit("missing translation for %r" % msgid)
            head = block[: block.index("msgstr")]
            out.append(head + "msgstr " + po_quote(row[col]))
        with open(os.path.join(I18N, lang + ".po"), "w", encoding="utf-8") as fh:
            fh.write("\n\n".join(out) + "\n")
        print("wrote i18n/%s.po (%d entries)" % (lang, len(out) - 1))


if __name__ == "__main__":
    main()
