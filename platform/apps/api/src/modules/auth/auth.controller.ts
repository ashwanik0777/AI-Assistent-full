import { Controller, Post, HttpCode, HttpStatus } from '@nestjs/common';
import { Public } from '../../common/decorators/public.decorator';

@Controller('auth')
export class AuthController {
  @Public()
  @Post('login')
  @HttpCode(HttpStatus.OK)
  login() {
    return { statusCode: 501, message: 'Not implemented' };
  }

  @Public()
  @Post('register')
  @HttpCode(HttpStatus.OK)
  register() {
    return { statusCode: 501, message: 'Not implemented' };
  }

  @Public()
  @Post('refresh')
  @HttpCode(HttpStatus.OK)
  refresh() {
    return { statusCode: 501, message: 'Not implemented' };
  }

  @Public()
  @Post('logout')
  @HttpCode(HttpStatus.OK)
  logout() {
    return { statusCode: 501, message: 'Not implemented' };
  }
}
