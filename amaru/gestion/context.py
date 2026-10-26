def navigation(request):
    u=request.user
    return {'staff_access':u.is_authenticated and u.has_perm('gestion.view_client'), 'admin_access':u.is_authenticated and u.has_perm('auth.change_user')}
