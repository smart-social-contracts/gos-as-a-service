import { LEGAL_CONTACT_EMAIL } from './legal-info.js';

/** Terms of Use for the Alpha, by locale. Each section: heading and paragraphs (plain text). */
export const TERMS = {
  en: {
    title: 'Terms of Use',
    alphaNotice: 'Alpha version. These terms are a plain-language draft and have not yet been reviewed by a lawyer.',
    sections: [
      {
        heading: '1. Who we are',
        paragraphs: [
          `gos.earth and realmsgos.org (the "Service") are operated by Smart Social Contracts. Contact: ${LEGAL_CONTACT_EMAIL}.`,
        ],
      },
      {
        heading: '2. This is an Alpha',
        paragraphs: [
          'The Service is an early test version. During the Alpha, nothing is charged. Credits are free, given by invitation, and have no cash value.',
          'Features change or disappear without notice, may not work, and are provided without any guarantee of availability. Data, realms and credits may be reset or deleted at any time. Do not rely on the Service for anything important, and do not put anything in it that you cannot afford to lose.',
        ],
      },
      {
        heading: '3. Access and your account',
        paragraphs: [
          'Access is by invitation. You sign in with Internet Identity; your account is the principal it gives you. Keep your Internet Identity safe: we cannot recover it for you.',
          'You must be at least 16 years old. Do not share your invitation code.',
        ],
      },
      {
        heading: '4. Realms are run by their members',
        paragraphs: [
          'A realm is a self-governed community running on the Internet Computer. Its rules, treasury and decisions belong to its members, not to us. We provide the software and the platform; we are not a party to what members agree, vote or spend, and we do not decide disputes between them.',
          'You are responsible for what you create, post or propose in a realm, and for complying with the law that applies to you.',
        ],
      },
      {
        heading: '5. The blockchain is permanent',
        paragraphs: [
          'Realms store their data on the Internet Computer, a public network of independent nodes. Data written there is replicated across nodes, may be readable by anyone, and can be very hard or impossible to delete or change, even by us. Think before you publish personal data on-chain. See the Privacy Policy.',
        ],
      },
      {
        heading: '6. AI features and AI assistants',
        paragraphs: [
          'The in-app assistant and any AI you connect through our MCP server can be wrong. Check what they tell you before you act on it.',
          'If you give an AI assistant a power of attorney, it can vote, submit proposals or propose treasury transactions for you within the permissions and dates you set. What it does is recorded as your own action. You are responsible for it. You can revoke a power of attorney at any time on the realm\'s "Power of attorney" page.',
        ],
      },
      {
        heading: '7. Acceptable use',
        paragraphs: [
          'Do not use the Service to break the law, harm others, attack or overload the platform, or try to get around its limits. We may suspend access or remove a realm that does so.',
        ],
      },
      {
        heading: '8. No warranty, limited liability',
        paragraphs: [
          'The Service is provided "as is". To the extent the law allows, we are not liable for losses arising from its use, including lost data, lost credits or decisions taken in a realm. Nothing in these terms limits liability that cannot be limited by law, such as for intent or gross negligence.',
        ],
      },
      {
        heading: '9. Changes, law and courts',
        paragraphs: [
          'We may change these terms; the date above shows the current version. If you keep using the Service after a change, you accept it. We may end the Alpha or your access at any time.',
          'Swiss law applies, excluding its conflict-of-law rules. Mandatory consumer protection rules in your country of residence remain unaffected.',
        ],
      },
    ],
  },
  es: {
    title: 'Términos de uso',
    alphaNotice: 'Versión Alpha. Estos términos son un borrador en lenguaje sencillo y aún no los ha revisado un abogado.',
    sections: [
      {
        heading: '1. Quiénes somos',
        paragraphs: [
          `gos.earth y realmsgos.org (el "Servicio") los opera Smart Social Contracts. Contacto: ${LEGAL_CONTACT_EMAIL}.`,
        ],
      },
      {
        heading: '2. Esto es una versión Alpha',
        paragraphs: [
          'El Servicio es una versión de prueba temprana. Durante el Alpha no se cobra nada. Los créditos son gratuitos, se dan por invitación y no tienen valor en dinero.',
          'Las funciones cambian o desaparecen sin aviso, pueden no funcionar y se ofrecen sin garantía de disponibilidad. Los datos, los realms y los créditos pueden reiniciarse o borrarse en cualquier momento. No dependa del Servicio para nada importante y no guarde en él nada que no pueda permitirse perder.',
        ],
      },
      {
        heading: '3. Acceso y su cuenta',
        paragraphs: [
          'El acceso es por invitación. Usted inicia sesión con Internet Identity; su cuenta es el principal que esta le asigna. Cuide su Internet Identity: no podemos recuperarla por usted.',
          'Debe tener al menos 16 años. No comparta su código de invitación.',
        ],
      },
      {
        heading: '4. Los realms los gestionan sus miembros',
        paragraphs: [
          'Un realm es una comunidad autogobernada que funciona en Internet Computer. Sus reglas, su tesorería y sus decisiones pertenecen a sus miembros, no a nosotros. Ofrecemos el software y la plataforma; no somos parte de lo que los miembros acuerdan, votan o gastan, y no resolvemos disputas entre ellos.',
          'Usted es responsable de lo que crea, publica o propone en un realm y de cumplir la ley que le sea aplicable.',
        ],
      },
      {
        heading: '5. La cadena de bloques es permanente',
        paragraphs: [
          'Los realms guardan sus datos en Internet Computer, una red pública de nodos independientes. Los datos escritos allí se replican entre nodos, pueden ser legibles por cualquiera y pueden ser muy difíciles o imposibles de borrar o modificar, incluso para nosotros. Piense antes de publicar datos personales en la cadena. Vea la Política de privacidad.',
        ],
      },
      {
        heading: '6. Funciones de IA y asistentes de IA',
        paragraphs: [
          'El asistente de la aplicación y cualquier IA que conecte mediante nuestro servidor MCP pueden equivocarse. Compruebe lo que le dicen antes de actuar.',
          'Si otorga un poder notarial a un asistente de IA, este puede votar, presentar propuestas o proponer transacciones de tesorería en su nombre, dentro de los permisos y las fechas que usted fije. Lo que haga queda registrado como acción suya y usted es responsable de ello. Puede revocar el poder en cualquier momento en la página "Poder notarial" del realm.',
        ],
      },
      {
        heading: '7. Uso aceptable',
        paragraphs: [
          'No use el Servicio para infringir la ley, perjudicar a otros, atacar o sobrecargar la plataforma ni eludir sus límites. Podemos suspender el acceso o retirar un realm que lo haga.',
        ],
      },
      {
        heading: '8. Sin garantía, responsabilidad limitada',
        paragraphs: [
          'El Servicio se ofrece "tal cual". En la medida en que la ley lo permita, no respondemos de pérdidas derivadas de su uso, incluidas la pérdida de datos o de créditos y las decisiones tomadas en un realm. Nada en estos términos limita la responsabilidad que la ley no permite limitar, como la derivada de dolo o negligencia grave.',
        ],
      },
      {
        heading: '9. Cambios, ley y tribunales',
        paragraphs: [
          'Podemos modificar estos términos; la fecha indicada muestra la versión vigente. Si sigue usando el Servicio tras un cambio, lo acepta. Podemos terminar el Alpha o su acceso en cualquier momento.',
          'Se aplica el derecho suizo, con exclusión de sus normas de conflicto de leyes. Las normas imperativas de protección del consumidor de su país de residencia no se ven afectadas.',
        ],
      },
    ],
  },
};
