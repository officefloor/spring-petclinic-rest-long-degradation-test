package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** cp08 telephone-e164: Change how the telephone is handled. Telephone numbers must now be stored in E.164 form: k... */
@Tag("cp08")
class Cp08Tests extends AcceptanceBase {

	@Test
	void coreNationalToE164() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "0412 345 678");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.telephone").value("+61412345678"));
	}

	@Test
	void functionalityKeepsExplicitCountryCode() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "+64 21 123 456");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.telephone").value("+6421123456"));
	}

	@Test
	void errorRejectsUnformattable() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "12");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
