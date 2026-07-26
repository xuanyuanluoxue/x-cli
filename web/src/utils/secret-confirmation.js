import { api } from "@/api/client.js";
import { useAuthStore } from "@/stores/auth.js";
import { confirmDialog, toast } from "@/utils/ui.js";

const CONFIG_KEY = "web_secret_confirmation";

export async function confirmSecretAccess(options) {
  const auth = useAuthStore();
  if (!auth.secretConfirmationRequired) return true;

  const result = await confirmDialog({
    ...options,
    checkboxLabel: `不再提示（可在配置文件中把 ${CONFIG_KEY} 改回 true）`,
  });
  if (!result.confirmed) return false;

  if (result.checked) {
    try {
      const preferences = await api.updatePreferences({
        secret_confirmation_required: false,
      });
      if (preferences.secret_confirmation_required === false) {
        auth.setSecretConfirmationRequired(false);
        toast("已关闭密钥安全确认，可在配置文件中重新开启", "success");
      }
    } catch (error) {
      toast(
        `已继续本次操作，但“不再提示”保存失败：${error.message}`,
        "error",
        4200,
      );
    }
  }
  return true;
}
