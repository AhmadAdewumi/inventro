from rest_framework import permissions

class IsManager(permissions.BasePermission):
    """
    Allows access to users in the Manager group or super users
    """
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True
        return request.user.groups.filter(name='Manager').exists()