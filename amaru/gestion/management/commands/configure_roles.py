from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group,Permission


class Command(BaseCommand):
    help='Configura cuatro roles sin crear usuarios ni credenciales.'
    def handle(self,*args,**options):
        policies={
            'Administrador':None,
            'Personal de atención':{
                'client':['view','add','change'],'prescription':['view','add'],
                'quote':['view','add','change'],'order':['view','add','change'],
                'warranty':['view','add','change'],'receipt':['view','add'],
                'inquiry':['view','change'],'inventory':['view','change'],
                'agreement':['view'],'request':['view','add','change']},
            'Taller':{'order':['view','change'],'warranty':['view','change'],'inventory':['view']},
            'Cliente':{},
        }
        for name,policy in policies.items():
            group,_=Group.objects.get_or_create(name=name)
            if policy is None:
                perms=Permission.objects.filter(content_type__app_label__in=['gestion','auth'])
            else:
                codes=[f'{verb}_{model}' for model,verbs in policy.items() for verb in verbs]
                perms=Permission.objects.filter(content_type__app_label='gestion',codename__in=codes)
            group.permissions.set(perms)
        self.stdout.write('Roles configurados. No se han creado usuarios ni contraseñas.')
