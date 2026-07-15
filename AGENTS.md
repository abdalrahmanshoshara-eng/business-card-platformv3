# AGENTS.md

قواعد إلزامية لأي تعديل على هذا المشروع:

- اقرأ `docs/ARCHITECTURE.md` قبل التعديل.
- لا تضع Business Logic في Views أو Pages (ضعه في `services/` أو `features/`).
- كل كرت يجب أن يخضع لقواعد الملكية (`cards_for_user`)؛ المالك من `request.user` فقط.
- كل Feature جديدة يجب أن تحتوي اختبارات.
- لا تعدّل Migration قديمة؛ أنشئ واحدة جديدة.
- لا تضف Dependency دون ضرورة؛ استخدم Django/الأدوات الموجودة.
- لا تخزن Authentication Tokens في localStorage أو sessionStorage.
- حافظ على الهوية البصرية الحالية (الألوان، الخطوط، الأزرار، RTL).
- شغّل الاختبارات وTypeScript build قبل إنهاء المهمة.
- حدّث `docs/ARCHITECTURE.md` عند تغيير المعمارية.
