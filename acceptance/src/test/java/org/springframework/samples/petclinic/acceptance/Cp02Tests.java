package org.springframework.samples.petclinic.acceptance;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import tools.jackson.databind.node.ObjectNode;

/** telephone-normalize: On create, normalize the telephone by removing every non-digit character, then require exa... */
@Tag("cp02")
class Cp02Tests extends AcceptanceBase {

	@Test
	void coreStripsToTenDigits() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "(04) 1234-5678");
		int id = createOwnerOk(o);
		getOwner(id).andExpect(jsonPath("$.telephone").value("0412345678"));
	}

	@Test
	void errorRejectsTooFewDigits() throws Exception {
		ObjectNode o = ownerNode();
		o.put("telephone", "12345");
		createOwner(o).andExpect(status().isBadRequest());
	}
}
