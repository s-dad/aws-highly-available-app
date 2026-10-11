# Screenshot checklist

Save screenshots in `docs/screenshots/` using these names so the README links work.

## Setup
- [ ] `01-vpc-subnets.png`: VPC with both public subnets and the route table
- [ ] `02-security-groups.png`: ALB and web security group rules
- [ ] `03-launch-template.png`: launch template summary (t2.micro, security group, LabInstanceProfile, user data)
- [ ] `04-alb-active.png`: load balancer with DNS name and Active status
- [ ] `05-asg-details.png`: Auto Scaling group details (min 1, desired 1, max 2)
- [ ] `06-running-instance.png`: one running instance
- [ ] `07-safeclick-browser.png`: SafeClick in the browser through the ALB DNS name, with a scan result

## Scaling
- [ ] `08-cloudwatch-cpu.png`: CloudWatch CPU climbing above 40%
- [ ] `09-asg-scale-out.png`: Activity tab showing the new instance launch
- [ ] `10-two-instances.png`: EC2 showing two running instances
- [ ] `11-two-instance-ids.png`: browser or curl loop showing both instance IDs
- [ ] `12-two-healthy-targets.png`: target group with two healthy targets

## Failure recovery
- [ ] `13-availability-loop.png`: terminal loop showing Status: 200 during the failure
- [ ] `14-asg-replacement.png`: Activity tab showing the replacement launch
- [ ] `15-target-group-recovery.png`: terminated target draining or unused, others healthy
- [ ] `16-final-state.png`: back to two healthy instances

## Documentation
- [ ] `architecture.png`: exported architecture diagram
