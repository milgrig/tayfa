"""Temporary script to register T009 result."""
import sys
sys.path.insert(0, "C:/Cursor/TayfaWindows/.tayfa/common")
from task_manager import set_task_result, update_task_status

set_task_result("T009", "Fixed kok/template_tayfa/hr/create_employee.py: removed ensure_dir for income/done/request and .gitkeep loop. Both files now clean.")
update_task_status("T009", "\u043d\u0430_\u043f\u0440\u043e\u0432\u0435\u0440\u043a\u0435")
print("T009 done")
