variable "region" {
  description = "AWS region. Learner Lab usually allows us-east-1 and us-west-2."
  type        = string
  default     = "us-east-1"
}

variable "ssh_cidr" {
  description = "Your public IP in CIDR form (for example 203.0.113.25/32). Only this address can SSH to the instances."
  type        = string

  validation {
    condition     = can(cidrhost(var.ssh_cidr, 0)) && var.ssh_cidr != "0.0.0.0/0"
    error_message = "Use your own IP as a /32, not 0.0.0.0/0."
  }
}

variable "key_name" {
  description = "Existing EC2 key pair. Learner Lab provides vockey."
  type        = string
  default     = "vockey"
}

variable "instance_profile_name" {
  description = "Existing IAM instance profile. Learner Lab blocks creating roles, so use its built-in LabInstanceProfile."
  type        = string
  default     = "LabInstanceProfile"
}

variable "instance_type" {
  description = "EC2 instance type for the web tier."
  type        = string
  default     = "t2.micro"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "Two public subnets in different Availability Zones (an ALB requires at least two)."
  type        = list(string)
  default     = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "asg_min" {
  type    = number
  default = 1
}

variable "asg_desired" {
  type    = number
  default = 1
}

variable "asg_max" {
  type    = number
  default = 2
}

variable "cpu_target" {
  description = "Average CPU utilization (%) the scaling policy tries to hold."
  type        = number
  default     = 40
}
